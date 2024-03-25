from dataclasses import dataclass, replace
from enum import Enum
import sys
import os
import time
import random
import keyboard

clear = lambda: os.system('cls')

@dataclass
class Exop:
    op: str
    mode: int
    arg: int

@dataclass
class Op:
    jump: bool
    opc: int
    modes: list[int]
    argn: int

class AMode(Enum):
    IMM = 1
    ABS = 2
    REL = 4

@dataclass
class CodeLine:
    line: str #to be able to concat
    label: str
    instr: list[str]
    comment: int
    asm: int
    pc: int
    to_link: bool

#################################################################################################################################
#### PARSE
#print(sys.argv)
lineno = 0
cparsed = []
do_run = True
with open(sys.argv[1], "r") as cin:
    for line in cin:
        stmt = line.rstrip()
        #find comment
        comment = ""
        if stmt.find(";") >= 0:
            cut = stmt.find(";")
            comment = stmt[cut:]
            stmt = stmt[:cut]
        #take the instruction list
        instr = [i.lower() for i in stmt.split(" ") if i != ""]
        #find label
        label = ""
        if len(instr) > 0 and instr[0][-1] == ":":
            label = instr[0][:-1]
            instr = instr[1:]
        #only take code relevant stuff
        if len(instr) > 0 or label != "":
            cparsed.append(CodeLine(str(lineno), label, instr, comment, 0, 0, False))
        lineno += 1
    cin.close()

#################################################################################################################################
#### ASM STATE 
mem = [0 for i in range(256)]
macrodefs = {}  #name - ([instr], [args])
labels = {}
#set/notset is bit14
#zero is 13
#carry 12
ops = {
    "br":  Op(True, 0xF000,[AMode.IMM, AMode.ABS],1),
    "bz":  Op(True, 0xE000,[AMode.IMM, AMode.ABS],1),
    "bnz": Op(True, 0xA000,[AMode.IMM, AMode.ABS],1),
    "bc":  Op(True, 0xD000,[AMode.IMM, AMode.ABS],1),
    "bnc": Op(True, 0x9000,[AMode.IMM, AMode.ABS],1),
    "sta": Op(False,0x2000,[AMode.ABS, AMode.REL],1),
    "lda": Op(False,0x0000,[AMode.IMM, AMode.ABS, AMode.REL],1),
    "or":  Op(False,0x0400,[AMode.IMM, AMode.ABS, AMode.REL],1),
    "xor": Op(False,0x0800,[AMode.IMM, AMode.ABS, AMode.REL],1),
    "and": Op(False,0x0C00,[AMode.IMM, AMode.ABS, AMode.REL],1),
    "not": Op(False,0x1000,[],0),
    "add": Op(False,0x1400,[AMode.IMM, AMode.ABS, AMode.REL],1),
    "rol": Op(False,0x1800,[AMode.IMM, AMode.ABS, AMode.REL],0),
    "ror": Op(False,0x1C00,[AMode.IMM, AMode.ABS, AMode.REL],0)
}

pc = 0
env = []
env.append({
    "__global__": True,
    "_vsp":     int("0xD0", 0),
    "_vsp_end": int("0xF0", 0)
})

def exists(name):
    for curr_env in reversed(env):
        if name in curr_env:
            return True
    return False

def lookup(name):
    for curr_env in reversed(env):
        if name in curr_env:
            return curr_env[name]
    raise RuntimeError

def getvsp():
    return env[-1]["_vsp"]

def decvsp():
    env[-1]["_vsp"] += 1
    if  env[-1]["_vsp"] >= env[0]["_vsp_end"]:
        print("ERROR: vsp space ran out")
        raise RuntimeError

#################################################################################################################################
#### ASSEMBLE
codelines = cparsed
quasi_asm = {}
while pc < len(codelines):
    stmt = codelines[pc]
    #handle special case with an empty line with no instructions but with a label, insert the label on the next line
    if len(stmt.instr) == 0:
        lbl = stmt.label
        codelines.pop(pc)
        stmt = codelines[pc]
        if stmt.label == "":
            stmt.label = lbl
        else:
            print("ERROR: merging multiple labels not yet supported: ", stmt)
            exit(1)
        continue
    if stmt.instr[0] in ops: #assemble!
        print("PC: " + str(pc) + "   ASSEMBLING: " + str(stmt))
        cpu_op = ops[stmt.instr[0]]
        stmt.asm = cpu_op.opc
        stmt.pc = pc
        quasi_asm[pc] = Exop(stmt.instr[0], 0 ,0)
        if len(stmt.instr) == 2 and cpu_op.argn == 1:
            arg = stmt.instr[1]
            argv = arg[1:]
            arg_assembled = 0
            if "__argenv" in env[-1] and arg in env[-1]["__argenv"]:
                print("INFO: doing substution of {} to {} in env {}".format(arg, env[-1]["__argenv"][arg], env[-1]))
                arg = env[-1]["__argenv"][arg]
                argv = arg[1:]
            if arg[0] == "#" and AMode.IMM in cpu_op.modes:
                arg_assembled = int(argv, 0)
                quasi_asm[pc].arg = arg_assembled
            elif ((arg[0] == "$" and AMode.ABS in cpu_op.modes) or (AMode.REL in cpu_op.modes and arg[0] == "*")) and cpu_op.jump == False:
                #absolute or relative
                #parse value as int or varname first
                is_var_ref = False
                try:
                    arg_assembled = int(argv, 0)
                    quasi_asm[pc].arg = arg_assembled
                except ValueError:
                    is_var_ref = True
                
                if is_var_ref:
                    #resolve variable addr
                    if exists(argv):
                        arg_assembled = lookup(argv)
                        quasi_asm[pc].arg = arg_assembled
                    else:
                        print("ERROR: unknown variable: ", stmt)
                        exit(1)
                if arg[0] == "$":
                    quasi_asm[pc].mode = 1
                    arg_assembled = arg_assembled | 256
                else:
                    arg_assembled = arg_assembled | 512
                    quasi_asm[pc].mode = 2
            elif cpu_op.jump == True:
                stmt.to_link = True
                quasi_asm[pc].mode = 1
            else:
                print("ERROR: wrong argument type: ", stmt, cpu_op)
                exit(1)
            stmt.asm = stmt.asm | arg_assembled
        elif len(stmt.instr) == 1 and cpu_op.argn == 0:
            #no args to parse
            pass
        else:
            print("ERROR: wrong amount of arguments when assembling: ", stmt, cpu_op)
            exit(1)

        if stmt.label != "":
            labels[stmt.label] = pc

        pc += 1
    elif stmt.instr[0] in macrodefs:
        #if its a macro, remove the call and substitute with body and continue assemmbling
        macro = macrodefs[stmt.instr[0]]
        stmt = codelines.pop(pc) #remove macro call
        #push env
        new_env = {}
        new_env["_vsp"] = getvsp()
        env.append(new_env)
        #match args if they are present
        call_args = stmt.instr[1:]
        argenv = {}
        if len(call_args) > 0:
            if len(call_args) != len(macro[0]):
                print("ERROR: trying to call macro with wrong arguments", stmt, macro)
                exit(1)
            for defname, callname in zip(macro[0], call_args):
                argenv[defname] = callname
        new_env["__argenv"] = argenv
        #TODO adjust codelines and labels to generate unique jump labels - skip for now?
        for bodyline in reversed(macro[1]):
            codelines.insert(pc, replace(bodyline))
        if stmt.label != "":
            if codelines[pc].label == "":
                codelines[pc].label = stmt.label
            else:
                print("ERROR: Macro cant have first line as label: ", stmt)
                exit(1)
    elif stmt.instr[0][0] == ".": #Special directive, dont forget to POP and dont touch PC
        instr = stmt.instr
        if instr[0] == ".def":
            macname = instr[1]
            if len(instr) > 2:
                args = instr[2:]
            else:
                args = []
            body = []
            codelines.pop(pc)
            while codelines[pc].instr[0] != ".end":
                body.append(codelines.pop(pc))
            body.append(CodeLine(codelines[pc].line, "", [".pop"], "", 0, 0, False))
            macrodefs[macname] = (args, body)
            codelines.pop(pc)
        elif instr[0] == ".var": #global vars go into first env
            name = instr[1]
            addr = int(instr[2], 0)
            global_env = env[0]
            global_env[name] = addr
            if len(instr) > 3:
                mem[addr] = int(instr[3], 0)
            codelines.pop(pc)
        elif instr[0] == ".pop":
            if len(env) == 1 or "__global__" in env[-1]:
                print("ERROR: trying to pop a global env", stmt)
                exit(1)
            env.pop()
            codelines.pop(pc)
        elif instr[0] == ".local":
            varname = instr[1]
            curr_env = env[-1]
            if varname in curr_env:
                print("ERROR: name clashed with top env", stmt, curr_env)
                exit(1)
            curr_env[varname] = getvsp()
            print("INFO: new local var {} at {:2X}".format(varname, getvsp()))
            decvsp()
            codelines.pop(pc)
    else:
        print("ERROR: unknown instr", stmt)
        exit(1)

#################################################################################################################################
#### LINK
for stmt in codelines:
    if stmt.to_link == True:
        if stmt.instr[1][0] != "$":
            print("ERROR link: expected absolute label as jump target", stmt)
            exit(1)
        arglabel = stmt.instr[1][1:]
        if arglabel in labels:
            addr = labels[arglabel]
            quasi_asm[stmt.pc].arg = addr
            stmt.asm = stmt.asm | addr
        else:
            print("ERROR link: label is not found in labels", stmt, arglabel, labels)
            exit(1)
#################################################################################################################################
#### DUMP
print("##############################")
print("WRITING DUMP")
with open("disass.dump", "w") as f:
    for cline in codelines:
        f.write("{:03X} : {:04X} ; STMT: {} \n".format(cline.pc, cline.asm, cline))
    f.close()
print("##############################")
print("WRITING ROM.HEX")
with open("rom.hex", "w") as f:
    f.write("v2.0 raw\n")
    for cline in codelines:
        f.write("{:04x}\n".format(cline.asm))
    f.close()
print("##############################")
#print(env)
print("##############################")
#print(quasi_asm)


sim_pc = 0
cycles = 0
sim_a = 0
sim_c = 0
sim_halted = False
disp = [ [0]*16 for i in range(16)]
disp_ctrl = 0
sim_delta = 0
last_pix_ts = 0

def get_pix():
    r = disp_ctrl & 0xF
    c = (disp_ctrl >> 4) & 0xF
    return disp[r][c]

def set_pix(v):
    global sim_delta
    global cycles
    global last_pix_ts
    r = disp_ctrl & 0xF
    c = (disp_ctrl >> 4) & 0xF
    disp[r][c] = v
    sim_delta =  cycles - last_pix_ts
    last_pix_ts = cycles

def show_disp():
    clear()
    print("")
    for i in range(0,16):
        for j in range(0,16):
            if disp[i][j] == 1:
                print(" #", end="")
            else:
                print(" .", end="")
        print("")

def show_mem():
    for j in range(0,16):
        print("{:02X} ".format(j), end="")
    print("")
    for i in range(0,16):
        print("{:02X}: ".format(i*16), end="")
        for j in range(0,16):
            print("{:02X} ".format(mem[i*16+j]), end="")
        print("")

while do_run and not sim_halted:
    instr = quasi_asm[sim_pc]
    mem_a = 0
    cycles += 2
    time.sleep(1/200)
    show_disp()
    print("PC: {:03X}, ACC: {:02X}, INSTR: {}".format(sim_pc, sim_a, instr))
    print("Cycles elapsed: {}, setpix delta: {}".format(cycles, sim_delta))
    #show_mem()
    if instr.op == "br":
        sim_pc = instr.arg
        continue
    if instr.op == "bz" and sim_a == 0:
        sim_pc = instr.arg
        continue
    if instr.op == "bnz" and sim_a != 0:
        sim_pc = instr.arg
        continue
    if instr.op == "bc" and sim_c == 1:
        sim_pc = instr.arg
        continue
    if instr.op == "bnc" and sim_c != 1:
        sim_pc = instr.arg
        continue

    if instr.mode == 0:
        argv = instr.arg & 0xFF
    elif instr.mode == 1:
        mem_a = instr.arg & 0xFF
        argv = mem[mem_a] & 0xFF
    elif instr.mode == 2:
        mem_a = instr.arg & 0xFF
        mem_a = mem[mem_a] & 0xFF
        argv = mem[mem_a] & 0xFF
        cycles += 2
    if instr.op == "lda":
        sim_a = argv & 0xFF
        if mem_a == 255:
            sim_halted = True
        if mem_a == 254:
            if keyboard.is_pressed("up"):
                sim_a = 1
            elif keyboard.is_pressed("right"):
                sim_a = 2
            elif keyboard.is_pressed("down"):
                sim_a = 4
            elif keyboard.is_pressed("left"):
                sim_a = 8
        if mem_a == 253:
            sim_a = random.randint(0, 255)
        if mem_a == 252:
            sim_a = disp_ctrl
        if mem_a == 251:
            sim_a = get_pix()
    if instr.op == "sta":
        mem[mem_a] = sim_a
        if mem_a == 255:
            sim_halted = True
        if mem_a == 252:
            disp_ctrl = sim_a
        if mem_a == 251:
            set_pix(sim_a)
    if instr.op == "or":
        sim_a = sim_a | argv
    elif instr.op == "xor":
        sim_a = sim_a ^ argv
    elif instr.op == "and":
        sim_a = sim_a & argv
    elif instr.op == "not":
        sim_a = ~sim_a
    elif instr.op == "add":
        sim_a = sim_a + argv
        sim_c = (sim_a & 0x100) >> 8
        sim_a &= 0xFF
    elif instr.op == "ror":
        newc = sim_a & 1
        sim_a =( sim_a >> 1) | (sim_c << 7)
        sim_a &= 0xFF
        sim_c = newc
    elif instr.op == "rol":
        newc = (sim_a & 80) >> 7
        sim_a = ((sim_a << 1)  & sim_c ) & 0xFF
        sim_c = newc
    
    sim_pc += 1

