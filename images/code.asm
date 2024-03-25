;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;;;;; macrodefs and helpers

.def mov a b
    lda a
    sta b
.end

.def clc
    lda #0
    rol
.end

.def setc
    lda #1
    ror
.end

.def sub b
    .local t
    .local t2
    sta $t
    lda b
    not
    add #1
    sta $t2
    clc
    lda $t2
    add $t ; -b + a
.end

;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;;;;; Globals

;    00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F
;00: 00 00 20 00 00 00 00 00 00 00 00 00 00 00 00 00
;10: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
;20: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
;30: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
;40: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
;50: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
;60: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
;70: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00

;; Snake data as head-tail list
;80: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
;90: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
;A0: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
;B0: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00

;C0: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 

;; D0 to EF are VSP temps
;D0: 03 20 FD 00 00 00 00 00 00 00 00 00 00 00 00 00
;E0: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00

;; SPECIALS
;F0: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 1D

.var halt    0xff ; <<<< MMIO RW   ANY ACCESS WILL HALT THE CLOCK
.var inp     0xfe ; <<<< MMIO RO   4 bit pressed keys bitwise
.var rnd     0xfd ; <<<< MMIO RO   8 bit rnd val
.var disprc  0xfc ; <<<< MMIO WO   7:4 ROW 3:0 COL
.var disppix 0xfb ; <<<< MMIO RW   bit 0
.var brk     0xfa ; <<<< MMIO RW   ANY ACCESS WILL BREAK

.var headp   0x10  ;pointer to HEAD grows up to CF then wraps 90
.var tailp   0x11  ;pointer to TAIL grows also up or dont
.var foodloc 0x12 
.var hdir    0x13  ;direction of head 1 up, 2 r, 4 dn, 8
.var headnext 0x14

br $main    ;;;;;;;;;; WE ALWAYS START WITH A TO MAIN

main:   lda #0x81
        sta $headp
        .local tmp 
        mov #0x80 $tailp
        mov #0xA7 *headp  ;same column, head is one up, two vertical positions
        mov #0xA8 *tailp
        mov #1 $hdir      ;dir up
        mov *tailp $disprc
        lda #1
        sta $disppix
        mov *headp $disprc
        lda #1
        sta $disppix

gen_food: lda $rnd
        sta $disprc
        sta $tmp
        lda $disppix
        bnz $gen_food  ;empty pixel - found place for new food
        mov #1 $disppix
        mov $tmp $foodloc

read_inp: clc
        lda $inp
        bz $use_old_dir
        sta $hdir
use_old_dir: lda $hdir
        ror
        bc $up
        ror 
        bc $right
        ror
        bc $down
        ror 
        bc $left
        br $gameover ; fatal err
up:     clc
        lda *headp ; up decs ROW
        add #0xFF
        and #0x0F
        sta $headnext
        lda *headp
        and #0xF0
        or $headnext
        sta $headnext
        br $check_next
down:   clc
        lda *headp ; down incs ROW
        add #0x01
        and #0x0F
        sta $headnext
        lda *headp
        and #0xF0
        or $headnext
        sta $headnext
        br $check_next
left:   clc
        lda *headp ; left dec COl
        add #0xF0
        and #0xF0
        sta $headnext
        lda *headp 
        and #0x0F
        or $headnext
        sta $headnext
        br $check_next
right:  clc
        lda *headp ; right inc COL
        add #0x10
        and #0xF0
        sta $headnext
        lda *headp 
        and #0x0F
        or $headnext
        sta $headnext
        br $check_next
check_next: ;;assuming next head is in headnext
        mov $headnext $disprc
        lda $disppix
        bz $next_empty
        ;; uhoh, its set. now compare it with food
        lda $headnext
        xor $foodloc
        bz $eat_food
        ;; oops. we took a bite of ourself
        br $gameover

next_empty: ;;hurra, all clearto move into new cel, $headnext is new head really and there was no food
        mov $headnext $disprc ;set pixel
        lda #1
        sta $disppix
        clc
        lda $headp            ;increase pointer and wrap it
        add #1
        and #0xBF ;wrap between 0x80 and BF
        sta $headp
        mov $headnext *headp  ;save head data
        lda $headp            ;check win
        xor $tailp
        bz $gamewin
        ;; remove tail
        mov *tailp $disprc
        lda #0
        sta $disppix
        ror ;clear carry
        lda $tailp
        add #1
        and #0xBF
        sta $tailp
        br $read_inp

eat_food: ;;; also good, headnext points to a food, which is a set pixel. move head, no tail
        clc
        lda $headp            ;increase pointer and wrap it
        add #1
        and #0xBF ;wrap between 0x80 and BF
        sta $headp
        mov $headnext *headp  ;save head data
        lda $headp            ;check win
        xor $tailp
        bz $gamewin
        br $gen_food
gamewin:  br $gameover
gameover: sta $halt