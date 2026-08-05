```
proc 18571
context binder
  thread 18657: l 10 need_return 0 tr 0
    outgoing transaction 837277473: 0000000000000000 from 18571:18657 to 2055:0 code 36 flags 12 pri 0:120 r1 elapsed 48738ms
    transaction complete
  thread 18666: l 11 need_return 0 tr 0
    outgoing transaction 837287344: 0000000000000000 from 18571:18666 to 2055:0 code 1 flags 12 pri 0:120 r1 elapsed 346ms
    transaction complete
  node 837244615: ub400007bfca38920 cb400007c4ca171d0 pri 0:139 hs 1 hw 1 ls 3 lw 0 is 1 iw 1 tr 1 proc 2055
    pending async transaction 837272957: 0000000000000000 from 2055:2093 to 18571:0 code 1 flags 11 pri 0:120 r0 elapsed 63512ms node 837244615 size 124:0 offset 180
    pending async transaction 837274967: 0000000000000000 from 2055:2093 to 18571:0 code 1 flags 11 pri 0:120 r0 elapsed 58785ms node 837244615 size 124:0 offset 0
  buffer 31968599: 0 size 124:0:0 active
  buffer 31965627: 100 size 124:0:0 delivered
  buffer 31966589: 180 size 124:0:0 active
```

```
proc 31727
context binder
  node 831990252: ub400007bfca32d70 cb400007c4ca0d450 pri 0:139 hs 1 hw 1 ls 7 lw 0 is 1 iw 1 tr 1 proc 2055
    pending async transaction 837172420: 0000000000000000 from 2055:2131 to 31727:0 code 1b flags 11 pri 0:120 r0 elapsed 156014ms node 831990252 size 80:0 offset 50
    pending async transaction 837210413: 0000000000000000 from 2055:2131 to 31727:0 code 1b flags 11 pri 0:120 r0 elapsed 120648ms node 831990252 size 80:0 offset a0
    pending async transaction 837211697: 0000000000000000 from 2055:2131 to 31727:0 code 1b flags 11 pri 0:120 r0 elapsed 119982ms node 831990252 size 80:0 offset f0
    pending async transaction 837233969: 0000000000000000 from 2055:2661 to 31727:0 code 23 flags 11 pri 0:120 r0 elapsed 107637ms node 831990252 size 128:8 offset 1e0
    pending async transaction 837234982: 0000000000000000 from 2055:3266 to 31727:0 code 25 flags 11 pri 0:120 r0 elapsed 106925ms node 831990252 size 128:8 offset 268
    pending async transaction 837261655: 0000000000000000 from 2055:3818 to 31727:0 code 22 flags 11 pri 0:120 r0 elapsed 87548ms node 831990252 size 128:8 offset 8a8
  node 831991097: ub400007bfca383b0 cb400007c4ca1ea90 pri 0:139 hs 1 hw 1 ls 2 lw 0 is 1 iw 1 tr 1 proc 2055
    pending async transaction 837262941: 0000000000000000 from 2055:2309 to 31727:0 code 1 flags 11 pri 0:120 r0 elapsed 86377ms node 831991097 size 1140:0 offset 930
  node 831991129: ub400007bfca41080 cb400007c4ca17ef0 pri 0:139 hs 1 hw 1 ls 9 lw 0 is 1 iw 1 tr 1 proc 2055
    pending async transaction 837249979: 0000000000000000 from 2055:2108 to 31727:0 code 2 flags 11 pri 0:120 r0 elapsed 97411ms node 831991129 size 156:0 offset 768
    pending async transaction 837261578: 0000000000000000 from 2055:2108 to 31727:0 code 2 flags 11 pri 0:120 r0 elapsed 87611ms node 831991129 size 156:0 offset 808
    pending async transaction 837265921: 0000000000000000 from 2055:2108 to 31727:0 code 2 flags 11 pri 0:120 r0 elapsed 82038ms node 831991129 size 156:0 offset da8
    pending async transaction 837269136: 0000000000000000 from 2055:2108 to 31727:0 code 2 flags 11 pri 0:120 r0 elapsed 75754ms node 831991129 size 156:0 offset e48
    pending async transaction 837270954: 0000000000000000 from 2055:2108 to 31727:0 code 2 flags 11 pri 0:120 r0 elapsed 69989ms node 831991129 size 156:0 offset ee8
    pending async transaction 837273282: 0000000000000000 from 2055:2108 to 31727:0 code 2 flags 11 pri 0:120 r0 elapsed 62099ms node 831991129 size 156:0 offset f88
    pending async transaction 837275230: 0000000000000000 from 2055:2108 to 31727:0 code 2 flags 11 pri 0:120 r0 elapsed 58522ms node 831991129 size 156:0 offset 1028
    pending async transaction 837276829: 0000000000000000 from 2055:2108 to 31727:0 code 2 flags 11 pri 0:120 r0 elapsed 51086ms node 831991129 size 156:0 offset 10c8
  buffer 31865731: 0 size 80:0:0 active
  buffer 31866052: 50 size 80:0:0 active
  buffer 31904045: a0 size 80:0:0 active
  buffer 31905329: f0 size 80:0:0 active
  buffer 31923548: 140 size 156:0:0 active
  buffer 31927601: 1e0 size 128:8:0 active
  buffer 31928614: 268 size 128:8:0 active
  buffer 31929495: 2f0 size 1140:0:0 active
  buffer 31943611: 768 size 156:0:0 active
  buffer 31955210: 808 size 156:0:0 active
  buffer 31955287: 8a8 size 128:8:0 active
  buffer 31956573: 930 size 1140:0:0 active
  buffer 31959553: da8 size 156:0:0 active
  buffer 31962768: e48 size 156:0:0 active
  buffer 31964586: ee8 size 156:0:0 active
  buffer 31966914: f88 size 156:0:0 active
  buffer 31968862: 1028 size 156:0:0 active
  buffer 31970461: 10c8 size 156:0:0 active
  node work 837104840: ub400007bfca50950 cb400007c4ca1a710
  pending transaction 837172099: 0000000000000000 from 2055:2131 to 31727:0 code 1b flags 11 pri 0:120 r0 elapsed 156104ms node 831990252 size 80:0 offset 0
  pending transaction 837229916: 0000000000000000 from 2055:2108 to 31727:0 code 2 flags 11 pri 0:120 r0 elapsed 110121ms node 831991129 size 156:0 offset 140
  pending transaction 837235863: 0000000000000000 from 2055:2309 to 31727:0 code 1 flags 11 pri 0:120 r0 elapsed 106159ms node 831991097 size 1140:0 offset 2f0
```

### system-server节点状态
```
proc 2055
context binder
  thread 2055: l 10 need_return 0 tr 0
    outgoing transaction 837286038: 0000000000000000 from 2055:2055 to 2867:3270 code db flags 10 pri 0:118 r1 elapsed 6712ms
    transaction complete
  thread 2078: l 02 need_return 1 tr 0
    incoming transaction 421626664: 0000000000000000 from 12540:12540 to 2055:2078 code 5f434d44 flags 10 pri 0:120 r1 elapsed 408774060ms node 6656 size 256:40 offset e00
  thread 2079: l 01 need_return 1 tr 0
    incoming transaction 653916247: 0000000000000000 from 10549:10549 to 2055:2079 code 5f434d44 flags 10 pri 0:120 r1 elapsed 166277104ms node 6656 size 256:40 offset 1820
  thread 2215: l 01 need_return 1 tr 0
    incoming transaction 435945103: 0000000000000000 from 21936:21936 to 2055:2215 code 5f434d44 flags 10 pri 0:120 r1 elapsed 392930812ms node 6656 size 260:40 offset fc8
  thread 2227: l 01 need_return 1 tr 0
    incoming transaction 465103751: 0000000000000000 from 32654:32654 to 2055:2227 code 5f434d44 flags 10 pri 0:120 r1 elapsed 365928060ms node 6656 size 260:40 offset 1348
  thread 2228: l 01 need_return 1 tr 0
    incoming transaction 370806097: 0000000000000000 from 10561:10561 to 2055:2228 code 5f434d44 flags 10 pri 0:120 r1 elapsed 473032692ms node 6656 size 256:40 offset cd8
  thread 2294: l 01 need_return 1 tr 0
    incoming transaction 649129919: 0000000000000000 from 7475:7475 to 2055:2294 code 5f434d44 flags 10 pri 0:120 r1 elapsed 170952857ms node 6656 size 256:40 offset 1c60
  thread 2295: l 01 need_return 1 tr 0
    incoming transaction 775202898: 0000000000000000 from 30869:30869 to 2055:2295 code 5f434d44 flags 10 pri 0:120 r1 elapsed 60419017ms node 6656 size 260:40 offset 2080
  thread 2329: l 10 need_return 0 tr 0
    outgoing transaction 837287442: 0000000000000000 from 2055:2329 to 1302:0 code 14 flags 10 pri 0:120 r1 elapsed 310ms
    transaction complete
  thread 2424: l 10 need_return 0 tr 1
    outgoing transaction 837287631: 0000000000000000 from 2055:2424 to 2576:0 code 5f flags 10 pri 0:118 r1 elapsed 0ms
    transaction complete
  thread 2480: l 01 need_return 1 tr 0
    incoming transaction 91960855: 0000000000000000 from 17187:17187 to 2055:2480 code 5f434d44 flags 10 pri 0:120 r1 elapsed 829129738ms node 6656 size 256:40 offset 300
  thread 2788: l 01 need_return 1 tr 0
    incoming transaction 324733848: 0000000000000000 from 27368:27368 to 2055:2788 code 5f434d44 flags 10 pri 0:120 r1 elapsed 524346768ms node 6656 size 260:40 offset a20
  thread 2789: l 01 need_return 1 tr 0
    incoming transaction 456821918: 0000000000000000 from 22135:22135 to 2055:2789 code 5f434d44 flags 10 pri 0:120 r1 elapsed 372587187ms node 6656 size 256:40 offset 1220
  thread 3031: l 01 need_return 0 tr 0
    incoming transaction 837270470: 0000000000000000 from 19370:19371 to 2055:3031 code 5f444d50 flags 10 pri 0:100 r1 elapsed 72085ms node 6688 size 28:8 offset cb0
  thread 3034: l 01 need_return 1 tr 0
    incoming transaction 446300457: 0000000000000000 from 14747:14747 to 2055:3034 code 5f434d44 flags 10 pri 0:120 r1 elapsed 383933942ms node 6656 size 256:40 offset 10f8
  thread 3035: l 01 need_return 1 tr 0
    incoming transaction 575486417: 0000000000000000 from 19062:19062 to 2055:3035 code 5f434d44 flags 10 pri 0:120 r1 elapsed 262939452ms node 6656 size 260:40 offset 1508
  thread 3036: l 01 need_return 0 tr 0
    incoming transaction 837270988: 0000000000000000 from 19384:19384 to 2055:3036 code 5f434d44 flags 10 pri 0:120 r1 elapsed 69871ms node 6656 size 416:40 offset 104b0
  thread 3037: l 01 need_return 1 tr 0
    incoming transaction 303172202: 0000000000000000 from 4865:4865 to 2055:3037 code 5f434d44 flags 10 pri 0:120 r1 elapsed 547026382ms node 6656 size 252:40 offset 8c8
  thread 3063: l 01 need_return 1 tr 0
    incoming transaction 588397018: 0000000000000000 from 13884:13884 to 2055:3063 code 5f434d44 flags 10 pri 0:120 r1 elapsed 244575748ms node 6656 size 256:40 offset 1a08
  thread 3105: l 01 need_return 1 tr 0
    incoming transaction 151803256: 0000000000000000 from 8157:8157 to 2055:3105 code 5f434d44 flags 10 pri 0:120 r1 elapsed 729761555ms node 6656 size 256:40 offset 588
  thread 3241: l 01 need_return 1 tr 0
    incoming transaction 413511405: 0000000000000000 from 30377:30377 to 2055:3241 code 5f434d44 flags 10 pri 0:120 r1 elapsed 415615409ms node 6656 size 260:40 offset b50
  thread 3243: l 01 need_return 0 tr 0
    incoming transaction 837275563: 0000000000000000 from 19031:19150 to 2055:3243 code 5f444d50 flags 10 pri 0:100 r1 elapsed 57313ms node 7781 size 88:8 offset 31e0
  thread 3253: l 01 need_return 0 tr 0
    incoming transaction 837274447: 0000000000000000 from 19497:19499 to 2055:3253 code 5f444d50 flags 10 pri 0:120 r1 elapsed 59127ms node 6666 size 28:8 offset 3a30
  thread 3254: l 01 need_return 1 tr 0
    incoming transaction 747933253: 0000000000000000 from 8001:8001 to 2055:3254 code 5f434d44 flags 10 pri 0:120 r1 elapsed 74280785ms node 6656 size 256:40 offset 33e0
  thread 3255: l 01 need_return 1 tr 0
    incoming transaction 105824695: 0000000000000000 from 24908:24908 to 2055:3255 code 5f434d44 flags 10 pri 0:120 r1 elapsed 805180458ms node 6656 size 260:40 offset 428
  thread 3256: l 01 need_return 1 tr 0
    incoming transaction 669666644: 0000000000000000 from 23003:23003 to 2055:3256 code 5f434d44 flags 10 pri 0:120 r1 elapsed 150249602ms node 6656 size 256:40 offset 1f58
  thread 3257: l 01 need_return 1 tr 0
    incoming transaction 286380409: 0000000000000000 from 7602:7602 to 2055:3257 code 5f434d44 flags 10 pri 0:120 r1 elapsed 567197343ms node 6656 size 256:40 offset 6e0
  thread 3264: l 01 need_return 1 tr 0
    incoming transaction 589869601: 0000000000000000 from 30474:30474 to 2055:3264 code 5f434d44 flags 10 pri 0:120 r1 elapsed 240261086ms node 6656 size 260:40 offset 1b30
  thread 3266: l 11 need_return 0 tr 0
    outgoing transaction 837275541: 0000000000000000 from 2055:3266 to 2867:3262 code bd flags 10 pri 0:120 r1 elapsed 57492ms
    incoming transaction 837270088: 0000000000000000 from 29399:29495 to 2055:3266 code 3 flags 10 pri 0:120 r1 elapsed 73165ms node 8165 size 524:8 offset e220
    transaction complete
  thread 3267: l 01 need_return 1 tr 0
    incoming transaction 607235158: 0000000000000000 from 21838:21838 to 2055:3267 code 5f434d44 flags 10 pri 0:120 r1 elapsed 219560274ms node 6656 size 260:40 offset 16c0
  thread 3818: l 01 need_return 0 tr 0
    incoming transaction 837272033: 0000000000000000 from 19420:19421 to 2055:3818 code 5f444d50 flags 10 pri 0:100 r1 elapsed 67079ms node 6673 size 28:8 offset 36b8
  thread 5375: l 01 need_return 1 tr 0
    incoming transaction 82455020: 0000000000000000 from 15612:15612 to 2055:5375 code 5f434d44 flags 10 pri 0:120 r1 elapsed 845509442ms node 6656 size 256:40 offset 1d8
  thread 5377: l 01 need_return 1 tr 0
    incoming transaction 69117142: 0000000000000000 from 1070:1070 to 2055:5377 code 5f434d44 flags 10 pri 0:120 r1 elapsed 866034747ms node 6656 size 260:40 offset 0
  thread 5425: l 01 need_return 1 tr 0
    incoming transaction 680902301: 0000000000000000 from 28853:28853 to 2055:5425 code 5f434d44 flags 10 pri 0:120 r1 elapsed 138721245ms node 6656 size 260:40 offset 1d88
  thread 20313: l 00 need_return 0 tr 1
    outgoing transaction 837287629: 0000000000000000 from 2055:20313 to 1214:7378 code 2 flags 10 pri 0:116 r1 elapsed 1ms
    transaction complete
  node 9472: ub400007bfca71200 cb400007c4ca54c10 pri 0:120 hs 1 hw 1 ls 36 lw 0 is 1 iw 1 tr 1 proc 1227
    pending async transaction 837277084: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49807ms node 9472 size 204:0 offset f790
    pending async transaction 837277127: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49617ms node 9472 size 204:0 offset b7b0
    pending async transaction 837277129: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49616ms node 9472 size 204:0 offset b880
    pending async transaction 837280944: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 30178ms node 9472 size 204:0 offset 199a8
    pending async transaction 837280945: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 30175ms node 9472 size 204:0 offset 19a78
    pending async transaction 837280957: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 30086ms node 9472 size 204:0 offset 19b48
    pending async transaction 837280958: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 30085ms node 9472 size 204:0 offset 19c18
    pending async transaction 837281139: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 29178ms node 9472 size 204:0 offset 1aaa0
    pending async transaction 837281140: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 29174ms node 9472 size 204:0 offset 1ab70
    pending async transaction 837281389: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 27991ms node 9472 size 204:0 offset 1c488
    pending async transaction 837281392: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 27989ms node 9472 size 204:0 offset 1c648
    pending async transaction 837281492: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 27708ms node 9472 size 204:0 offset 1d090
    pending async transaction 837281494: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 27705ms node 9472 size 204:0 offset 1d160
    pending async transaction 837281499: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 27671ms node 9472 size 204:0 offset 1d230
    pending async transaction 837281500: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 27670ms node 9472 size 204:0 offset 1d300
    pending async transaction 837282515: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 21597ms node 9472 size 204:0 offset 1e7e8
    pending async transaction 837282516: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 21595ms node 9472 size 204:0 offset 1e8b8
    pending async transaction 837282561: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 21294ms node 9472 size 204:0 offset 1e988
    pending async transaction 837282562: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 21291ms node 9472 size 204:0 offset 1ea58
    pending async transaction 837285248: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 10059ms node 9472 size 204:0 offset 20590
    pending async transaction 837285249: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 10058ms node 9472 size 204:0 offset 20660
    pending async transaction 837285272: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 9887ms node 9472 size 204:0 offset 20730
    pending async transaction 837285273: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 9882ms node 9472 size 204:0 offset 20800
    pending async transaction 837285330: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 9632ms node 9472 size 204:0 offset 20c90
    pending async transaction 837285331: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 9624ms node 9472 size 204:0 offset 20d60
    pending async transaction 837285373: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 9308ms node 9472 size 204:0 offset 20e30
    pending async transaction 837285374: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 9307ms node 9472 size 204:0 offset 20f00
    pending async transaction 837285451: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 8894ms node 9472 size 204:0 offset 21390
    pending async transaction 837285452: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 8893ms node 9472 size 204:0 offset 21460
    pending async transaction 837285482: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 8698ms node 9472 size 204:0 offset 215a8
    pending async transaction 837285483: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 8697ms node 9472 size 204:0 offset 21678
    pending async transaction 837285622: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 8042ms node 9472 size 204:0 offset 22488
    pending async transaction 837285625: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 8041ms node 9472 size 204:0 offset 22558
    pending async transaction 837285667: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 7816ms node 9472 size 204:0 offset 22628
    pending async transaction 837285668: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 7814ms node 9472 size 204:0 offset 226f8
  node 7969: ub400007bfca86a70 cb400007c4ca56fb0 pri 0:120 hs 1 hw 1 ls 6 lw 0 is 1 iw 1 tr 1 proc 1195
    pending async transaction 837278266: 0000000000000000 from 1195:1204 to 2055:0 code 2 flags 11 pri 0:120 r0 elapsed 45668ms node 7969 size 156:0 offset 102b0
    pending async transaction 837280126: 0000000000000000 from 1195:1204 to 2055:0 code 2 flags 11 pri 0:120 r0 elapsed 35665ms node 7969 size 156:0 offset db60
    pending async transaction 837281850: 0000000000000000 from 1195:1204 to 2055:0 code 2 flags 11 pri 0:120 r0 elapsed 25660ms node 7969 size 156:0 offset 12808
    pending async transaction 837284082: 0000000000000000 from 1195:1204 to 2055:0 code 2 flags 11 pri 0:120 r0 elapsed 15658ms node 7969 size 156:0 offset 1fef0
    pending async transaction 837286199: 0000000000000000 from 1195:1204 to 2055:0 code 2 flags 11 pri 0:120 r0 elapsed 5656ms node 7969 size 156:0 offset 4da0
  node 17240: ub400007bfca9e7d0 cb400007c4ca93190 pri 0:120 hs 1 hw 1 ls 41 lw 0 is 1 iw 1 tr 1 proc 1247
    pending async transaction 837268564: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 76761ms node 17240 size 152:0 offset 5548
    pending async transaction 837269142: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 75760ms node 17240 size 152:0 offset 8430
    pending async transaction 837269400: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 74759ms node 17240 size 152:0 offset 93f8
    pending async transaction 837269752: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 73755ms node 17240 size 152:0 offset bba0
    pending async transaction 837270257: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 72756ms node 17240 size 152:0 offset f4b0
    pending async transaction 837270580: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 71752ms node 17240 size 152:0 offset fef8
    pending async transaction 837270767: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 70751ms node 17240 size 152:0 offset 10070
    pending async transaction 837271009: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 69749ms node 17240 size 152:0 offset 10678
    pending async transaction 837271160: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 68747ms node 17240 size 152:0 offset 10788
    pending async transaction 837271707: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 67745ms node 17240 size 152:0 offset 12770
    pending async transaction 837272097: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 66715ms node 17240 size 152:0 offset 4fc8
    pending async transaction 837272359: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 65714ms node 17240 size 152:0 offset 14ae8
    pending async transaction 837272576: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 64713ms node 17240 size 152:0 offset 14d28
    pending async transaction 837272831: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 63712ms node 17240 size 152:0 offset 14e38
    pending async transaction 837273113: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 62710ms node 17240 size 152:0 offset 16cf0
    pending async transaction 837273418: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 61708ms node 17240 size 152:0 offset 16e58
    pending async transaction 837273825: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 60708ms node 17240 size 152:0 offset 8260
    pending async transaction 837274219: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 59707ms node 17240 size 152:0 offset 69d8
    pending async transaction 837275055: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 58700ms node 17240 size 152:0 offset 6c88
    pending async transaction 837275447: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 57698ms node 17240 size 152:0 offset 29b8
    pending async transaction 837275670: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 56697ms node 17240 size 152:0 offset 2340
    pending async transaction 837275840: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 55694ms node 17240 size 152:0 offset 37f8
    pending async transaction 837276061: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 54693ms node 17240 size 152:0 offset 3560
    pending async transaction 837276259: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 53692ms node 17240 size 152:0 offset 2830
    pending async transaction 837276508: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 52691ms node 17240 size 152:0 offset 3b70
    pending async transaction 837276712: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 51689ms node 17240 size 152:0 offset 28c8
    pending async transaction 837276904: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 50688ms node 17240 size 152:0 offset e168
    pending async transaction 837277109: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49685ms node 17240 size 152:0 offset b598
    pending async transaction 837277501: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 48686ms node 17240 size 152:0 offset 79a0
    pending async transaction 837277712: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 47686ms node 17240 size 152:0 offset f3f8
    pending async transaction 837277972: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 46684ms node 17240 size 152:0 offset fe58
    pending async transaction 837278261: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 45683ms node 17240 size 152:0 offset 10190
    pending async transaction 837278459: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 44681ms node 17240 size 152:0 offset ca10
    pending async transaction 837278667: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 43681ms node 17240 size 152:0 offset cc20
    pending async transaction 837278989: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 42680ms node 17240 size 152:0 offset cef0
    pending async transaction 837279134: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 41678ms node 17240 size 152:0 offset d000
    pending async transaction 837279292: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 40677ms node 17240 size 152:0 offset d120
    pending async transaction 837279447: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 39675ms node 17240 size 152:0 offset d230
    pending async transaction 837279670: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 38673ms node 17240 size 152:0 offset d4f0
    pending async transaction 837279822: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 37670ms node 17240 size 152:0 offset d8c8
  node 88742: ub400007bfcab8a50 cb400007c4ca6aed0 pri 0:120 hs 1 hw 1 ls 4 lw 0 is 1 iw 1 tr 1 proc 1384
    pending async transaction 837277539: 0000000000000000 from 1384:1399 to 2055:0 code 3 flags 11 pri 0:120 r0 elapsed 48551ms node 88742 size 1380:0 offset c120
    pending async transaction 837278662: 0000000000000000 from 1384:1399 to 2055:0 code 3 flags 11 pri 0:120 r0 elapsed 43689ms node 88742 size 376:0 offset caa8
    pending async transaction 837281549: 0000000000000000 from 1384:1399 to 2055:0 code 3 flags 11 pri 0:120 r0 elapsed 27469ms node 88742 size 1380:0 offset 1d790
  node 7686: ub400007bfcabdac0 cb400007c4ca35a10 pri 0:120 hs 1 hw 1 ls 3 lw 0 is 1 iw 1 tr 1 proc 1490
    pending async transaction 837269863: 0000000000000000 from 1490:2174 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 73538ms node 7686 size 112:0 offset 2fd0
    pending async transaction 837269881: 0000000000000000 from 1490:2174 to 2055:0 code 8 flags 11 pri 0:120 r0 elapsed 73537ms node 7686 size 108:0 offset 3040
  node 7352: ub400007bfcac1d50 cb400007c5cb09a58 pri 0:120 hs 1 hw 1 ls 6 lw 0 is 1 iw 1 tr 1 proc 1316
    pending async transaction 837271864: 0000000000000000 from 1316:2260 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 67197ms node 7352 size 6400:104 offset 12d60
    pending async transaction 837272967: 0000000000000000 from 1316:2260 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 63602ms node 7352 size 6800:120 offset 15058
    pending async transaction 837274522: 0000000000000000 from 1316:2260 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 59048ms node 7352 size 6004:88 offset 16f68
    pending async transaction 837275044: 0000000000000000 from 1316:2260 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 58728ms node 7352 size 4396:64 offset 18738
    pending async transaction 837287237: 0000000000000000 from 1316:2260 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 658ms node 7352 size 3960:56 offset 23988
  node 7079: ub400007bfcac1d80 cb400007c4ca40990 pri 0:120 hs 1 hw 1 ls 102 lw 0 is 1 iw 1 tr 1 proc 1221
    pending async transaction 837271234: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 68653ms node 7079 size 240:0 offset 10820
    pending async transaction 837272299: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 65972ms node 7079 size 240:0 offset 50d8
    pending async transaction 837272303: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 65970ms node 7079 size 240:0 offset 51c8
    pending async transaction 837272309: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 65955ms node 7079 size 240:0 offset 14728
    pending async transaction 837272311: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 65953ms node 7079 size 240:0 offset 14818
    pending async transaction 837272317: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 65916ms node 7079 size 240:0 offset 14908
    pending async transaction 837272321: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 65913ms node 7079 size 240:0 offset 149f8
    pending async transaction 837277134: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49610ms node 7079 size 240:0 offset b950
    pending async transaction 837277136: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49608ms node 7079 size 240:0 offset ba40
    pending async transaction 837277140: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49606ms node 7079 size 240:0 offset 3fb0
    pending async transaction 837277143: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49604ms node 7079 size 240:0 offset 40a0
    pending async transaction 837277147: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49602ms node 7079 size 240:0 offset 4190
    pending async transaction 837277150: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49600ms node 7079 size 240:0 offset 4280
    pending async transaction 837277167: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49578ms node 7079 size 240:0 offset 4370
    pending async transaction 837277174: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49574ms node 7079 size 240:0 offset 4460
    pending async transaction 837277180: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49570ms node 7079 size 240:0 offset 4550
    pending async transaction 837277183: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49568ms node 7079 size 240:0 offset 4640
    pending async transaction 837277187: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49566ms node 7079 size 240:0 offset 7110
    pending async transaction 837277192: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49563ms node 7079 size 240:0 offset 7200
    pending async transaction 837277271: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49281ms node 7079 size 240:0 offset 78b0
    pending async transaction 837277273: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49281ms node 7079 size 240:0 offset e438
    pending async transaction 837277282: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49277ms node 7079 size 240:0 offset e528
    pending async transaction 837277284: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49276ms node 7079 size 240:0 offset e618
    pending async transaction 837277298: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49265ms node 7079 size 240:0 offset e708
    pending async transaction 837277304: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49264ms node 7079 size 240:0 offset e7f8
    pending async transaction 837277317: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49259ms node 7079 size 240:0 offset ebd0
    pending async transaction 837277320: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49258ms node 7079 size 240:0 offset ecc0
    pending async transaction 837277322: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49257ms node 7079 size 240:0 offset edb0
    pending async transaction 837277330: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49254ms node 7079 size 240:0 offset efd8
    pending async transaction 837277332: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49253ms node 7079 size 240:0 offset f0c8
    pending async transaction 837277335: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49252ms node 7079 size 240:0 offset f1b8
    pending async transaction 837279572: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 39005ms node 7079 size 240:0 offset d340
    pending async transaction 837279711: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 38374ms node 7079 size 240:0 offset d588
    pending async transaction 837279713: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 38372ms node 7079 size 240:0 offset d678
    pending async transaction 837280967: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 30073ms node 7079 size 240:0 offset 19ce8
    pending async transaction 837280969: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 30070ms node 7079 size 240:0 offset 19dd8
    pending async transaction 837280971: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 30068ms node 7079 size 240:0 offset 19ec8
    pending async transaction 837280975: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 30067ms node 7079 size 240:0 offset 19fb8
    pending async transaction 837281035: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 29741ms node 7079 size 240:0 offset 1a6e0
    pending async transaction 837281039: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 29740ms node 7079 size 240:0 offset 1a7d0
    pending async transaction 837281044: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 29737ms node 7079 size 240:0 offset 1a8c0
    pending async transaction 837281046: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 29735ms node 7079 size 240:0 offset 1a9b0
    pending async transaction 837281180: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 28938ms node 7079 size 240:0 offset 1ac40
    pending async transaction 837281182: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 28936ms node 7079 size 240:0 offset 1ad30
    pending async transaction 837281184: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 28934ms node 7079 size 240:0 offset 1ae20
    pending async transaction 837281188: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 28933ms node 7079 size 240:0 offset 1af10
    pending async transaction 837281193: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 28932ms node 7079 size 240:0 offset 1b000
    pending async transaction 837281195: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 28931ms node 7079 size 240:0 offset 1b0f0
    pending async transaction 837281274: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 28543ms node 7079 size 240:0 offset 1b1e0
    pending async transaction 837281278: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 28542ms node 7079 size 240:0 offset 1b2d0
    pending async transaction 837281287: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 28526ms node 7079 size 240:0 offset 1b3c0
    pending async transaction 837281298: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 28515ms node 7079 size 240:0 offset 1b4b0
    pending async transaction 837281391: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 27989ms node 7079 size 240:0 offset 1c558
    pending async transaction 837281398: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 27987ms node 7079 size 240:0 offset 1c718
    pending async transaction 837281401: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 27986ms node 7079 size 240:0 offset 1c808
    pending async transaction 837281403: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 27985ms node 7079 size 240:0 offset 1c8f8
    pending async transaction 837281417: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 27965ms node 7079 size 240:0 offset 1c9e8
    pending async transaction 837281425: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 27959ms node 7079 size 240:0 offset 1cdc0
    pending async transaction 837281430: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 27956ms node 7079 size 240:0 offset 1ceb0
    pending async transaction 837281435: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 27953ms node 7079 size 240:0 offset 1cfa0
    pending async transaction 837281504: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 27659ms node 7079 size 240:0 offset 1d3d0
    pending async transaction 837281509: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 27658ms node 7079 size 240:0 offset 1d4c0
    pending async transaction 837281511: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 27657ms node 7079 size 240:0 offset 1d5b0
    pending async transaction 837281514: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 27656ms node 7079 size 240:0 offset 1d6a0
    pending async transaction 837281576: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 27307ms node 7079 size 240:0 offset 1e2b8
    pending async transaction 837281581: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 27306ms node 7079 size 240:0 offset 1e3a8
    pending async transaction 837281587: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 27297ms node 7079 size 240:0 offset 1e498
    pending async transaction 837281594: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 27294ms node 7079 size 240:0 offset 1e588
    pending async transaction 837282574: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 21264ms node 7079 size 240:0 offset 1eb28
    pending async transaction 837282579: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 21259ms node 7079 size 240:0 offset 1ec18
    pending async transaction 837282702: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 21001ms node 7079 size 240:0 offset 1ee80
    pending async transaction 837282796: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 20922ms node 7079 size 240:0 offset 1f530
    pending async transaction 837282808: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 20917ms node 7079 size 240:0 offset 1f620
    pending async transaction 837283632: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 17870ms node 7079 size 240:0 offset 1fb28
    pending async transaction 837283634: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 17869ms node 7079 size 240:0 offset 1fc18
    pending async transaction 837285151: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 10263ms node 7079 size 240:0 offset 20428
    pending async transaction 837285284: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 9870ms node 7079 size 240:0 offset 208d0
    pending async transaction 837285286: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 9869ms node 7079 size 240:0 offset 209c0
    pending async transaction 837285291: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 9865ms node 7079 size 240:0 offset 20ab0
    pending async transaction 837285295: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 9864ms node 7079 size 240:0 offset 20ba0
    pending async transaction 837285396: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 9182ms node 7079 size 240:0 offset 20fd0
    pending async transaction 837285400: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 9175ms node 7079 size 240:0 offset 210c0
    pending async transaction 837285403: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 9173ms node 7079 size 240:0 offset 211b0
    pending async transaction 837285410: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 9167ms node 7079 size 240:0 offset 212a0
    pending async transaction 837285489: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 8676ms node 7079 size 240:0 offset 21748
    pending async transaction 837285496: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 8670ms node 7079 size 240:0 offset 21838
    pending async transaction 837285502: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 8664ms node 7079 size 240:0 offset 21928
    pending async transaction 837285507: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 8658ms node 7079 size 240:0 offset 21a18
    pending async transaction 837285563: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 8323ms node 7079 size 240:0 offset 220c8
    pending async transaction 837285565: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 8322ms node 7079 size 240:0 offset 221b8
    pending async transaction 837285569: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 8317ms node 7079 size 240:0 offset 222a8
    pending async transaction 837285571: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 8316ms node 7079 size 240:0 offset 22398
    pending async transaction 837285682: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 7775ms node 7079 size 240:0 offset 227c8
    pending async transaction 837285686: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 7774ms node 7079 size 240:0 offset 228b8
    pending async transaction 837285688: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 7773ms node 7079 size 240:0 offset 229a8
    pending async transaction 837285695: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 7766ms node 7079 size 240:0 offset 22a98
    pending async transaction 837285752: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 7423ms node 7079 size 240:0 offset 23148
    pending async transaction 837285754: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 7422ms node 7079 size 240:0 offset 23238
    pending async transaction 837285756: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 7420ms node 7079 size 240:0 offset 23328
    pending async transaction 837285758: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 7419ms node 7079 size 240:0 offset 23418
    pending async transaction 837285838: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 7211ms node 7079 size 240:0 offset 23580
  node 7103: ub400007bfcac4a50 cb400007c4ca3a4b0 pri 0:120 hs 1 hw 1 ls 21 lw 0 is 1 iw 1 tr 1 proc 1250
    pending async transaction 837277173: 0000000000000000 from 1250:1271 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49574ms node 7103 size 736:0 offset 6e30
    pending async transaction 837277268: 0000000000000000 from 1250:1271 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49287ms node 7103 size 736:0 offset 72f0
    pending async transaction 837277269: 0000000000000000 from 1250:1271 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49286ms node 7103 size 736:0 offset 75d0
    pending async transaction 837277307: 0000000000000000 from 1250:1271 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49263ms node 7103 size 740:0 offset e8e8
    pending async transaction 837281030: 0000000000000000 from 1250:1271 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 29747ms node 7103 size 736:0 offset 1a120
    pending async transaction 837281031: 0000000000000000 from 1250:1271 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 29746ms node 7103 size 736:0 offset 1a400
    pending async transaction 837281310: 0000000000000000 from 1250:1271 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 28482ms node 7103 size 736:0 offset 1b618
    pending async transaction 837281373: 0000000000000000 from 1250:1271 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 28066ms node 7103 size 736:0 offset 1b8f8
    pending async transaction 837281386: 0000000000000000 from 1250:1271 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 27994ms node 7103 size 736:0 offset 1bbd8
    pending async transaction 837281387: 0000000000000000 from 1250:1271 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 27994ms node 7103 size 736:0 offset 1beb8
    pending async transaction 837281388: 0000000000000000 from 1250:1271 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 27992ms node 7103 size 752:0 offset 1c198
    pending async transaction 837281419: 0000000000000000 from 1250:1271 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 27963ms node 7103 size 740:0 offset 1cad8
    pending async transaction 837281569: 0000000000000000 from 1250:1271 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 27319ms node 7103 size 736:0 offset 1dcf8
    pending async transaction 837281570: 0000000000000000 from 1250:1271 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 27319ms node 7103 size 736:0 offset 1dfd8
    pending async transaction 837282783: 0000000000000000 from 1250:1271 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 20937ms node 7103 size 736:0 offset 1ef70
    pending async transaction 837282788: 0000000000000000 from 1250:1271 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 20934ms node 7103 size 736:0 offset 1f250
    pending async transaction 837285553: 0000000000000000 from 1250:1271 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 8338ms node 7103 size 736:0 offset 21b08
    pending async transaction 837285554: 0000000000000000 from 1250:1271 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 8337ms node 7103 size 736:0 offset 21de8
    pending async transaction 837285742: 0000000000000000 from 1250:1271 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 7442ms node 7103 size 736:0 offset 22b88
    pending async transaction 837285743: 0000000000000000 from 1250:1271 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 7441ms node 7103 size 736:0 offset 22e68
  node 42347: ub400007bfcadaec0 cb400007c9ca34ff8 pri 0:120 hs 1 hw 1 ls 5 lw 0 is 1 iw 1 tr 1 proc 1316
    pending async transaction 837272932: 0000000000000000 from 1316:1757 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 63619ms node 42347 size 372:16 offset 14ed0
    pending async transaction 837273537: 0000000000000000 from 1316:1316 to 2055:0 code 2 flags 11 pri 0:120 r0 elapsed 61343ms node 42347 size 160:8 offset 7ba0
    pending async transaction 837274510: 0000000000000000 from 1316:1757 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 59065ms node 42347 size 392:24 offset 6a70
    pending async transaction 837275224: 0000000000000000 from 1316:1757 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 58578ms node 42347 size 392:24 offset b280
  node 6656: ub400007bfcae5690 cb400007c4ca3de10 pri 0:120 hs 1 hw 1 ls 65 lw 0 is 105 iw 105 tr 1 proc 20184 20141 20100 19687 3884 19384 18571 18552 18138 18107 16412 16157 16057 15796 15597 15527 15450 14428 13854 12745 12384 12254 11690 11375 11258 9331 8688 7982 7739 6167 6130 6003 5153 4096 3317 30810 30978 21259 22022 14237 9106 31727 31354 30854 22455 16834 16066 12591 26693 1888 1716 28822 12066 9779 10280 30869 8001 8274 25802 25993 4195 28853 23003 30857 10549 7475 29399 21838 30474 13884 19062 32654 22135 14747 21936 12540 30377 10561 27368 4865 7602 8157 24908 17187 15612 1070 16454 11321 5055 5075 4973 4937 4464 3796 2923 2903 2885 2867 2796 2712 2576 1302 1490 1511 447
    pending async transaction 837266324: 0000000000000000 from 15251:15360 to 2055:0 code 19 flags 11 pri 0:120 r0 elapsed 81585ms node 6656 size 124:8 offset 36e8
    pending async transaction 837266596: 0000000000000000 from 4915:6038 to 2055:0 code 19 flags 11 pri 0:120 r0 elapsed 80598ms node 6656 size 124:8 offset 3158
    pending async transaction 837268768: 0000000000000000 from 5902:5902 to 2055:0 code 19 flags 11 pri 0:120 r0 elapsed 76282ms node 6656 size 124:8 offset 5720
    pending async transaction 837269885: 0000000000000000 from 1490:2174 to 2055:0 code b flags 11 pri 0:120 r0 elapsed 73537ms node 6656 size 88:0 offset 3918
    pending async transaction 837270028: 0000000000000000 from 12916:12916 to 2055:0 code 19 flags 11 pri 0:120 r0 elapsed 73184ms node 6656 size 124:8 offset deb8
    pending async transaction 837270054: 0000000000000000 from 15251:15251 to 2055:0 code 3f flags 11 pri 0:120 r0 elapsed 73174ms node 6656 size 120:8 offset 2738
    pending async transaction 837270056: 0000000000000000 from 15251:15251 to 2055:0 code 3f flags 11 pri 0:120 r0 elapsed 73174ms node 6656 size 120:8 offset 3778
    pending async transaction 837270651: 0000000000000000 from 22461:22501 to 2055:0 code 19 flags 11 pri 0:120 r0 elapsed 71513ms node 6656 size 124:8 offset ffe8
    pending async transaction 837270838: 0000000000000000 from 20893:20893 to 2055:0 code 19 flags 11 pri 0:120 r0 elapsed 70579ms node 6656 size 124:8 offset 10360
    pending async transaction 837271887: 0000000000000000 from 2885:2885 to 2055:0 code 103 flags 11 pri 0:120 r0 elapsed 67185ms node 6656 size 92:0 offset 146c8
    pending async transaction 837273041: 0000000000000000 from 31835:31870 to 2055:0 code 19 flags 11 pri 0:120 r0 elapsed 63182ms node 6656 size 124:8 offset 16b60
    pending async transaction 837273495: 0000000000000000 from 12649:10373 to 2055:0 code 19 flags 11 pri 0:120 r0 elapsed 61483ms node 6656 size 124:8 offset 5358
    pending async transaction 837273515: 0000000000000000 from 26486:26486 to 2055:0 code 3f flags 11 pri 0:120 r0 elapsed 61353ms node 6656 size 264:8 offset 53e0
    pending async transaction 837273518: 0000000000000000 from 26486:26486 to 2055:0 code 3f flags 11 pri 0:120 r0 elapsed 61352ms node 6656 size 120:8 offset 55e0
    pending async transaction 837273911: 0000000000000000 from 4937:4937 to 2055:0 code 19 flags 11 pri 0:120 r0 elapsed 60545ms node 6656 size 124:8 offset 8d08
    pending async transaction 837275498: 0000000000000000 from 29399:29503 to 2055:0 code 103 flags 11 pri 0:120 r0 elapsed 57534ms node 6656 size 92:0 offset 1eb8
    pending async transaction 837275739: 0000000000000000 from 26486:18023 to 2055:0 code 19 flags 11 pri 0:120 r0 elapsed 56272ms node 6656 size 124:8 offset 32d8
    pending async transaction 837276345: 0000000000000000 from 3819:3941 to 2055:0 code 19 flags 11 pri 0:120 r0 elapsed 53175ms node 6656 size 124:8 offset df40
    pending async transaction 837276753: 0000000000000000 from 29457:29605 to 2055:0 code 19 flags 11 pri 0:120 r0 elapsed 51463ms node 6656 size 124:8 offset 2e30
    pending async transaction 837278126: 0000000000000000 from 1870:3204 to 2055:0 code 19 flags 11 pri 0:120 r0 elapsed 46246ms node 6656 size 124:8 offset 10108
    pending async transaction 837279184: 0000000000000000 from 14865:14865 to 2055:0 code 19 flags 11 pri 0:120 r0 elapsed 41438ms node 6656 size 124:8 offset d098
    pending async transaction 837280048: 0000000000000000 from 2867:3939 to 2055:0 code 19 flags 11 pri 0:120 r0 elapsed 36228ms node 6656 size 124:8 offset d9d8
    pending async transaction 837280513: 0000000000000000 from 11192:11247 to 2055:0 code 19 flags 11 pri 0:120 r0 elapsed 33106ms node 6656 size 124:8 offset dcf8
    pending async transaction 837280761: 0000000000000000 from 29902:30126 to 2055:0 code 19 flags 11 pri 0:120 r0 elapsed 31427ms node 6656 size 124:8 offset 198a8
    pending async transaction 837282285: 0000000000000000 from 5055:5055 to 2055:0 code 19 flags 11 pri 0:120 r0 elapsed 23101ms node 6656 size 124:8 offset 12b30
    pending async transaction 837287293: 0000000000000000 from 4937:4937 to 2055:0 code 19 flags 11 pri 0:120 r0 elapsed 529ms node 6656 size 124:8 offset 52b8
  node 26057: ub400007bfcb51090 cb400007c4cad9630 pri 0:120 hs 1 hw 1 ls 2 lw 0 is 1 iw 1 tr 1 proc 2796
    pending async transaction 837287271: 0000000000000000 from 2796:2862 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 639ms node 26057 size 276:0 offset 24e30
  node 26170: ub400007bfcb9b0d0 cb400007c4ca63490 pri 0:120 hs 1 hw 1 ls 2 lw 0 is 1 iw 1 tr 1 proc 2796
    pending async transaction 837287268: 0000000000000000 from 2796:2862 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 639ms node 26170 size 276:0 offset 24d18
  node 26205: ub400007bfcb9c4e0 cb400007c4ca72370 pri 0:120 hs 1 hw 1 ls 5 lw 0 is 1 iw 1 tr 1 proc 1197
    pending async transaction 837280529: 0000000000000000 from 1197:1210 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 33022ms node 26205 size 108:8 offset dd80
    pending async transaction 837281304: 0000000000000000 from 1197:1210 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 28503ms node 26205 size 108:8 offset 1b5a0
    pending async transaction 837284166: 0000000000000000 from 1197:1210 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 15083ms node 26205 size 108:8 offset 20010
    pending async transaction 837286450: 0000000000000000 from 1197:1210 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 4278ms node 26205 size 108:8 offset 4ec0
  node 26208: ub400007bfcb9cc60 cb400007c4ca63c70 pri 0:120 hs 1 hw 1 ls 4 lw 0 is 1 iw 1 tr 1 proc 1197
    pending async transaction 837279840: 0000000000000000 from 1197:1210 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 37528ms node 26208 size 108:8 offset d960
    pending async transaction 837283320: 0000000000000000 from 1197:1210 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 19587ms node 26208 size 108:8 offset 1fa38
    pending async transaction 837285468: 0000000000000000 from 1197:1210 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 8782ms node 26208 size 108:8 offset 21530
  node 24687: ub400007bfcbb02b0 cb400007c4ca9fcd0 pri 0:120 hs 1 hw 1 ls 4 lw 0 is 1 iw 1 tr 1 proc 1197
    pending async transaction 837280076: 0000000000000000 from 1197:1210 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 36026ms node 24687 size 108:8 offset da60
    pending async transaction 837283540: 0000000000000000 from 1197:1210 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 18086ms node 24687 size 108:8 offset 1fab0
    pending async transaction 837285790: 0000000000000000 from 1197:1210 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 7281ms node 24687 size 108:8 offset 23508
  node 14040: ub400007bfcbb4510 cb400007c4cab6c50 pri 0:120 hs 1 hw 1 ls 16 lw 0 is 2 iw 2 tr 1 proc 1195 447
    pending async transaction 837272462: 0000000000000000 from 1195:1230 to 2055:0 code 3 flags 11 pri 0:120 r0 elapsed 65421ms node 14040 size 124:0 offset 14ca8
    pending async transaction 837275846: 0000000000000000 from 1195:1204 to 2055:0 code 5 flags 11 pri 0:120 r0 elapsed 55671ms node 14040 size 136:0 offset 3890
    pending async transaction 837276087: 0000000000000000 from 1195:1230 to 2055:0 code 3 flags 11 pri 0:120 r0 elapsed 54575ms node 14040 size 124:0 offset 35f8
    pending async transaction 837278265: 0000000000000000 from 1195:1204 to 2055:0 code 5 flags 11 pri 0:120 r0 elapsed 45669ms node 14040 size 136:0 offset 10228
    pending async transaction 837278317: 0000000000000000 from 1195:1230 to 2055:0 code 3 flags 11 pri 0:120 r0 elapsed 45418ms node 14040 size 124:0 offset c990
    pending async transaction 837280125: 0000000000000000 from 1195:1204 to 2055:0 code 5 flags 11 pri 0:120 r0 elapsed 35666ms node 14040 size 136:0 offset dad8
    pending async transaction 837280160: 0000000000000000 from 1195:1230 to 2055:0 code 3 flags 11 pri 0:120 r0 elapsed 35402ms node 14040 size 124:0 offset dc00
    pending async transaction 837281849: 0000000000000000 from 1195:1204 to 2055:0 code 5 flags 11 pri 0:120 r0 elapsed 25662ms node 14040 size 136:0 offset 109a0
    pending async transaction 837281879: 0000000000000000 from 1195:19901 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 25434ms node 14040 size 220:0 offset 128a8
    pending async transaction 837281883: 0000000000000000 from 1195:1230 to 2055:0 code 3 flags 11 pri 0:120 r0 elapsed 25427ms node 14040 size 124:0 offset 12a30
    pending async transaction 837282015: 0000000000000000 from 1195:1230 to 2055:0 code 3 flags 11 pri 0:120 r0 elapsed 24398ms node 14040 size 124:0 offset 12ab0
    pending async transaction 837284081: 0000000000000000 from 1195:1204 to 2055:0 code 5 flags 11 pri 0:120 r0 elapsed 15659ms node 14040 size 136:0 offset 1fe68
    pending async transaction 837284123: 0000000000000000 from 1195:1230 to 2055:0 code 3 flags 11 pri 0:120 r0 elapsed 15405ms node 14040 size 124:0 offset 1ff90
    pending async transaction 837286198: 0000000000000000 from 1195:1204 to 2055:0 code 5 flags 11 pri 0:120 r0 elapsed 5657ms node 14040 size 136:0 offset 49e0
    pending async transaction 837286239: 0000000000000000 from 1195:1230 to 2055:0 code 3 flags 11 pri 0:120 r0 elapsed 5390ms node 14040 size 124:0 offset 4e40
  node 24506: ub400007bfcbb7e10 cb400007c4cae24b0 pri 0:120 hs 1 hw 1 ls 4 lw 0 is 1 iw 1 tr 1 proc 1197
    pending async transaction 837279547: 0000000000000000 from 1197:1210 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 39031ms node 24506 size 108:8 offset d2c8
    pending async transaction 837282640: 0000000000000000 from 1197:1210 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 21088ms node 24506 size 108:8 offset 10710
    pending async transaction 837285121: 0000000000000000 from 1197:1210 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 10283ms node 24506 size 108:8 offset 203b0
  node 24515: ub400007bfcbc5af0 cb400007c4cacea70 pri 0:120 hs 1 hw 1 ls 4 lw 0 is 1 iw 1 tr 1 proc 1197
    pending async transaction 837280742: 0000000000000000 from 1197:1210 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 31520ms node 24515 size 108:8 offset ddf8
    pending async transaction 837284465: 0000000000000000 from 1197:1210 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 13582ms node 24515 size 108:8 offset 202c0
    pending async transaction 837286716: 0000000000000000 from 1197:1210 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 2778ms node 24515 size 108:8 offset 4f38
  node 24586: ub400007bfcbc6b70 cb400007c4caa88b0 pri 0:120 hs 1 hw 1 ls 4 lw 0 is 1 iw 1 tr 1 proc 1197
    pending async transaction 837280322: 0000000000000000 from 1197:1210 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 34524ms node 24586 size 108:8 offset dc80
    pending async transaction 837283920: 0000000000000000 from 1197:1210 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 16585ms node 24586 size 108:8 offset 1fd08
    pending async transaction 837286180: 0000000000000000 from 1197:1210 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 5780ms node 24586 size 108:8 offset 4968
  node 11143: ub400007bfcbcb580 cb400007c4cab0ad0 pri 0:120 hs 1 hw 1 ls 2 lw 0 is 2 iw 2 tr 1 proc 1316 447
    pending async transaction 837273551: 0000000000000000 from 1316:1316 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 61339ms node 11143 size 208:0 offset 57a8
  node 24524: ub400007bfcbef190 cb400007c4cace110 pri 0:120 hs 1 hw 1 ls 4 lw 0 is 1 iw 1 tr 1 proc 1197
    pending async transaction 837280992: 0000000000000000 from 1197:1210 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 30019ms node 24524 size 108:8 offset 1a0a8
    pending async transaction 837284735: 0000000000000000 from 1197:1210 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 12082ms node 24524 size 108:8 offset 20338
    pending async transaction 837286998: 0000000000000000 from 1197:1210 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 1277ms node 24524 size 108:8 offset 23910
  node 21146: ub400007bfcbfafe0 cb400007c4caea490 pri 0:120 hs 1 hw 1 ls 1 lw 0 is 1 iw 1 tr 1 proc 1195
  node 48886: ub400007bfccb4290 cb400007c4cb02df0 pri 0:120 hs 1 hw 1 ls 2 lw 0 is 1 iw 1 tr 1 proc 2867
    pending async transaction 837287267: 0000000000000000 from 2867:2883 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 640ms node 48886 size 276:0 offset 24a50
  node 48695: ub400007bfccb43b0 cb400007c4cafcf10 pri 0:120 hs 1 hw 1 ls 2 lw 0 is 1 iw 1 tr 1 proc 2867
    pending async transaction 837287266: 0000000000000000 from 2867:2883 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 640ms node 48695 size 276:0 offset 24938
  node 49146: ub400007bfccc3ce0 cb400007c4caf37f0 pri 0:120 hs 1 hw 1 ls 2 lw 0 is 1 iw 1 tr 1 proc 2867
    pending async transaction 837287269: 0000000000000000 from 2867:3542 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 639ms node 49146 size 212:0 offset 24b68
  node 49176: ub400007bfccd5020 cb400007c4cb02130 pri 0:120 hs 1 hw 1 ls 2 lw 0 is 1 iw 1 tr 1 proc 2867
    pending async transaction 837287270: 0000000000000000 from 2867:3542 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 639ms node 49176 size 212:0 offset 24c40
  node 837278871: ub400007bfd819400 cb400007d0ccf6a68 pri 0:120 hs 1 hw 1 ls 1 lw 0 is 0 iw 0 tr 1
  node 837276185: ub400007bfd82a680 cb400007d0cc9e958 pri 0:120 hs 1 hw 1 ls 1 lw 0 is 0 iw 0 tr 1
  node 837286110: ub400007bfda2ecb0 cb400007d0cc2c0d8 pri 0:120 hs 1 hw 1 ls 1 lw 0 is 0 iw 0 tr 1
  node 837286817: ub400007bfdab3eb0 cb400007d0cc06fb8 pri 0:120 hs 1 hw 1 ls 2 lw 1 is 0 iw 0 tr 1
  node 837283160: ub400007bfdb40100 cb400007d0cdc7b18 pri 0:120 hs 1 hw 1 ls 1 lw 0 is 0 iw 0 tr 1
  node 837284295: ub400007bfdb41450 cb400007d0cd86c58 pri 0:120 hs 1 hw 1 ls 1 lw 0 is 0 iw 0 tr 1
  buffer 69117142: 0 size 260:40:0 active
  buffer 69117148: 130 size 36:8:0 delivered
  buffer 82455088: 160 size 36:8:0 delivered
  buffer 91960861: 190 size 36:8:0 delivered
  buffer 82455020: 1d8 size 256:40:0 active
  buffer 91960855: 300 size 256:40:0 active
  buffer 105824695: 428 size 260:40:0 active
  buffer 105824704: 558 size 36:8:0 delivered
  buffer 17585528: 588 size 256:40:0 active
  buffer 17585534: 6b0 size 36:8:0 delivered
  buffer 17944953: 6e0 size 256:40:0 active
  buffer 17944965: 808 size 36:8:0 delivered
  buffer 56298400: 838 size 36:8:0 delivered
  buffer 102370676: 868 size 36:8:0 delivered
  buffer 10858229: 898 size 36:8:0 delivered
  buffer 34736746: 8c8 size 252:40:0 active
  buffer 34736756: 9f0 size 36:8:0 delivered
  buffer 56298392: a20 size 260:40:0 active
  buffer 10858221: b50 size 260:40:0 active
  buffer 18973488: c80 size 36:8:0 delivered
  buffer 31964102: cb0 size 28:8:0 active
  buffer 102370641: cd8 size 256:40:0 active
  buffer 18973480: e00 size 256:40:0 active
  buffer 33291938: f28 size 36:8:0 delivered
  buffer 43647284: f58 size 36:8:0 delivered
  buffer 54168742: f88 size 36:8:0 delivered
  buffer 33291919: fc8 size 260:40:0 active
  buffer 43647273: 10f8 size 256:40:0 active
  buffer 54168734: 1220 size 256:40:0 active
  buffer 62450567: 1348 size 260:40:0 active
  buffer 62450588: 1478 size 36:8:0 delivered
  buffer 38615517: 14a8 size 36:8:0 delivered
  buffer 51526125: 14d8 size 36:8:0 delivered
  buffer 38615505: 1508 size 260:40:0 active
  buffer 70364257: 1638 size 36:8:0 delivered
  buffer 31973065: 1668 size 28:8:0 active
  buffer 52998728: 1690 size 36:8:0 delivered
  buffer 70364246: 16c0 size 260:40:0 active
  buffer 112259046: 17f0 size 36:8:0 delivered
  buffer 117045335: 1820 size 256:40:0 active
  buffer 117045342: 1948 size 36:8:0 delivered
  buffer 132795765: 1978 size 36:8:0 delivered
  buffer 9813669: 19a8 size 36:8:0 delivered
  buffer 104114267: 19d8 size 36:8:0 delivered
  buffer 51526106: 1a08 size 256:40:0 active
  buffer 52998689: 1b30 size 260:40:0 active
  buffer 112259007: 1c60 size 256:40:0 active
  buffer 9813661: 1d88 size 260:40:0 active
  buffer 31969130: 1eb8 size 92:0:0 active
  buffer 31975796: 1f18 size 40:8:0 active
  buffer 132795732: 1f58 size 256:40:0 active
  buffer 104114258: 2080 size 260:40:0 active
  buffer 31981244: 21b0 size 96:0:0 active
  buffer 31981232: 2210 size 112:0:0 active
  buffer 31980028: 2280 size 28:8:0 active
  buffer 31980938: 22a8 size 104:0:0 active
  buffer 31981188: 2310 size 28:8:0 active
  buffer 31969302: 2340 size 152:0:0 active
  buffer 31970021: 23d8 size 92:0:0 active
  buffer 31959903: 2668 size 108:8:0 delivered
  buffer 31974981: 26e0 size 84:0:0 active
  buffer 31963686: 2738 size 120:8:0 active
  buffer 31969812: 27b8 size 108:8:0 active
  buffer 31969891: 2830 size 152:0:0 active
  buffer 31970344: 28c8 size 152:0:0 active
  buffer 31971520: 2960 size 28:8:0 active
  buffer 76844811: 2988 size 36:8:0 delivered
  buffer 31969079: 29b8 size 152:0:0 active
  buffer 31981264: 2a50 size 380:24:0 delivered
  buffer 31969830: 2bf8 size 536:32:0 active
  buffer 31970385: 2e30 size 124:8:0 active
  buffer 31970469: 2eb8 size 104:0:0 active
  buffer 31970473: 2f20 size 104:0:0 active
  buffer 31974784: 2f88 size 28:8:0 active
  buffer 31963495: 2fd0 size 112:0:0 active
  buffer 31963513: 3040 size 108:0:0 active
  buffer 31981033: 30b0 size 152:0:0 active
  buffer 31960228: 3158 size 124:8:0 active
  buffer 31969195: 31e0 size 88:8:0 active
  buffer 31973580: 3240 size 28:8:0 active
  buffer 31980934: 3268 size 104:0:0 active
  buffer 31969371: 32d8 size 124:8:0 active
  buffer 31969488: 3360 size 108:8:0 active
  buffer 31970125: 33d8 size 0:0:0 active
  buffer 76844613: 33e0 size 256:40:0 active
  buffer 31969693: 3560 size 152:0:0 active
  buffer 31969719: 35f8 size 124:0:0 active
  buffer 31970258: 3678 size 40:8:0 active
  buffer 31965665: 36b8 size 28:8:0 active
  buffer 31969207: 36e0 size 0:0:0 active
  buffer 31959956: 36e8 size 124:8:0 active
  buffer 31963688: 3778 size 120:8:0 active
  buffer 31969472: 37f8 size 152:0:0 active
  buffer 31969478: 3890 size 136:0:0 active
  buffer 31963517: 3918 size 88:0:0 active
  buffer 31969236: 3970 size 108:8:0 active
  buffer 31977263: 39e8 size 28:8:0 active
  buffer 31968079: 3a30 size 28:8:0 active
  buffer 31969479: 3a58 size 156:0:0 active
  buffer 31969688: 3af8 size 108:8:0 active
  buffer 31970140: 3b70 size 152:0:0 active
  buffer 31975684: 3c08 size 48:8:0 active
  buffer 31968812: 3c48 size 108:8:0 active
  buffer 31970764: 3cc0 size 752:0:0 active
  buffer 31970772: 3fb0 size 240:0:0 active
  buffer 31970775: 40a0 size 240:0:0 active
  buffer 31970779: 4190 size 240:0:0 active
  buffer 31970782: 4280 size 240:0:0 active
  buffer 31970799: 4370 size 240:0:0 active
  buffer 31970806: 4460 size 240:0:0 active
  buffer 31970812: 4550 size 240:0:0 active
  buffer 31970815: 4640 size 240:0:0 active
  buffer 31969255: 4730 size 40:8:0 active
  buffer 31970153: 4760 size 108:8:0 active
  buffer 31979643: 4888 size 212:8:0 active
  buffer 31979812: 4968 size 108:8:0 active
  buffer 31979830: 49e0 size 136:0:0 active
  buffer 31977038: 4a88 size 28:8:0 active
  buffer 31961560: 4ad0 size 152:0:0 active
  buffer 31979748: 4b68 size 536:32:0 active
  buffer 31979831: 4da0 size 156:0:0 active
  buffer 31979871: 4e40 size 124:0:0 active
  buffer 31980082: 4ec0 size 108:8:0 active
  buffer 31980348: 4f38 size 108:8:0 active
  buffer 31965729: 4fc8 size 152:0:0 active
  buffer 31965931: 50d8 size 240:0:0 active
  buffer 31965935: 51c8 size 240:0:0 active
  buffer 31980925: 52b8 size 124:8:0 active
  buffer 31967127: 5358 size 124:8:0 active
  buffer 31967147: 53e0 size 264:8:0 active
  buffer 31962196: 5548 size 152:0:0 active
  buffer 31967150: 55e0 size 120:8:0 active
  buffer 31980932: 5660 size 104:0:0 active
  buffer 31962400: 5720 size 124:8:0 active
  buffer 31967183: 57a8 size 208:0:0 active
  buffer 31967851: 69d8 size 152:0:0 active
  buffer 31968142: 6a70 size 392:24:0 active
  buffer 31968687: 6c88 size 152:0:0 active
  buffer 31981237: 6d20 size 228:0:0 active
  buffer 31970805: 6e30 size 736:0:0 active
  buffer 31970819: 7110 size 240:0:0 active
  buffer 31970824: 7200 size 240:0:0 active
  buffer 31970900: 72f0 size 736:0:0 active
  buffer 31970901: 75d0 size 736:0:0 active
  buffer 31970903: 78b0 size 240:0:0 active
  buffer 31971133: 79a0 size 152:0:0 active
  buffer 31974705: 7a38 size 28:8:0 active
  buffer 31980948: 7a60 size 152:0:0 active
  buffer 31980962: 7af8 size 104:0:0 active
  buffer 31967169: 7ba0 size 160:8:0 active
  buffer 31980986: 7c48 size 248:8:0 active
  buffer 31967457: 8260 size 152:0:0 active
  buffer 31981032: 82f8 size 152:0:0 active
  buffer 31980995: 8390 size 152:0:0 active
  buffer 31962774: 8430 size 152:0:0 active
  buffer 31980997: 84c8 size 144:0:0 active
  buffer 31980999: 8558 size 152:0:0 active
  buffer 31980984: 8648 size 104:0:0 active
  buffer 31980788: 86d0 size 132:0:0 active
  buffer 31980797: 8758 size 132:0:0 active
  buffer 31980939: 87e0 size 104:0:0 active
  buffer 31981001: 8848 size 152:0:0 active
  buffer 31981051: 88e0 size 152:0:0 active
  buffer 31981052: 8978 size 152:0:0 active
  buffer 31981061: 8a10 size 124:8:0 active
  buffer 31967543: 8d08 size 124:8:0 active
  buffer 31981035: 8d90 size 152:0:0 active
  buffer 31981048: 8e28 size 152:0:0 active
  buffer 31981049: 8ec0 size 152:0:0 active
  buffer 31981050: 8f58 size 172:0:0 active
  buffer 31981063: 9008 size 152:0:0 active
  buffer 31981039: 90b8 size 152:0:0 active
  buffer 31981044: 9150 size 172:0:0 active
  buffer 31981068: 9200 size 152:0:0 active
  buffer 31981131: 9298 size 208:8:0 active
  buffer 31967722: 9370 size 108:8:0 active
  buffer 31963032: 93f8 size 152:0:0 active
  buffer 31980978: 9490 size 156:0:0 active
  buffer 31980982: 9530 size 104:0:0 active
  buffer 31980983: 9598 size 104:0:0 active
  buffer 31981229: 9600 size 88:0:0 active
  buffer 31963168: 9658 size 96:0:0 active
  buffer 31981208: 96b8 size 444:8:0 active
  buffer 31981212: 9880 size 112:0:0 active
  buffer 31972712: 98f0 size 28:8:0 active
  buffer 31968856: b280 size 392:24:0 active
  buffer 31981238: b420 size 304:8:0 active
  buffer 31970741: b598 size 152:0:0 active
  buffer 31970746: b630 size 384:0:0 active
  buffer 31970759: b7b0 size 204:0:0 active
  buffer 31970761: b880 size 204:0:0 active
  buffer 31970766: b950 size 240:0:0 active
  buffer 31970768: ba40 size 240:0:0 active
  buffer 31972752: bb30 size 100:0:0 active
  buffer 31963384: bba0 size 152:0:0 active
  buffer 31971128: bc38 size 1256:0:0 active
  buffer 31971171: c120 size 1380:0:0 active
  buffer 31971495: c688 size 212:0:0 active
  buffer 31971496: c760 size 276:0:0 active
  buffer 31971497: c878 size 276:0:0 active
  buffer 31971949: c990 size 124:0:0 active
  buffer 31972091: ca10 size 152:0:0 active
  buffer 31972294: caa8 size 376:0:0 active
  buffer 31972299: cc20 size 152:0:0 active
  buffer 31972510: ccb8 size 536:32:0 active
  buffer 31972621: cef0 size 152:0:0 active
  buffer 31972723: cf88 size 120:0:0 active
  buffer 31972766: d000 size 152:0:0 active
  buffer 31972816: d098 size 124:8:0 active
  buffer 31972924: d120 size 152:0:0 active
  buffer 31972970: d1b8 size 112:8:0 active
  buffer 31973079: d230 size 152:0:0 active
  buffer 31973179: d2c8 size 108:8:0 active
  buffer 31973204: d340 size 240:0:0 active
  buffer 31973253: d430 size 96:0:0 active
  buffer 31973255: d490 size 96:0:0 active
  buffer 31973302: d4f0 size 152:0:0 active
  buffer 31973343: d588 size 240:0:0 active
  buffer 31973345: d678 size 240:0:0 active
  buffer 31973411: d768 size 100:0:0 active
  buffer 31973414: d7d0 size 100:0:0 active
  buffer 31973444: d838 size 144:0:0 active
  buffer 31973454: d8c8 size 152:0:0 active
  buffer 31973472: d960 size 108:8:0 active
  buffer 31973680: d9d8 size 124:8:0 active
  buffer 31973708: da60 size 108:8:0 active
  buffer 31973757: dad8 size 136:0:0 active
  buffer 31973758: db60 size 156:0:0 active
  buffer 31973792: dc00 size 124:0:0 active
  buffer 31973954: dc80 size 108:8:0 active
  buffer 31974145: dcf8 size 124:8:0 active
  buffer 31974161: dd80 size 108:8:0 active
  buffer 31974374: ddf8 size 108:8:0 active
  buffer 31977433: de70 size 64:8:0 active
  buffer 31963660: deb8 size 124:8:0 active
  buffer 31969977: df40 size 124:8:0 active
  buffer 31970478: dfc8 size 104:0:0 active
  buffer 31970482: e030 size 104:0:0 active
  buffer 31970481: e098 size 104:0:0 active
  buffer 31970486: e100 size 104:0:0 active
  buffer 31970536: e168 size 152:0:0 active
  buffer 31963720: e220 size 524:8:0 active
  buffer 31970905: e438 size 240:0:0 active
  buffer 31970914: e528 size 240:0:0 active
  buffer 31970916: e618 size 240:0:0 active
  buffer 31970930: e708 size 240:0:0 active
  buffer 31970936: e7f8 size 240:0:0 active
  buffer 31970939: e8e8 size 740:0:0 active
  buffer 31970949: ebd0 size 240:0:0 active
  buffer 31970952: ecc0 size 240:0:0 active
  buffer 31970954: edb0 size 240:0:0 active
  buffer 31970956: eea0 size 312:0:0 active
  buffer 31970962: efd8 size 240:0:0 active
  buffer 31970964: f0c8 size 240:0:0 active
  buffer 31970967: f1b8 size 240:0:0 active
  buffer 31971158: f2a8 size 292:40:0 active
  buffer 31971344: f3f8 size 152:0:0 active
  buffer 31963889: f4b0 size 152:0:0 active
  buffer 31970475: f548 size 104:0:0 active
  buffer 31970579: f5b0 size 112:8:0 active
  buffer 31970677: f628 size 140:8:0 active
  buffer 31970715: f6c0 size 204:0:0 active
  buffer 31970716: f790 size 204:0:0 active
  buffer 31971105: f860 size 136:0:0 active
  buffer 31964091: f8f0 size 240:0:0 active
  buffer 31971452: f9e0 size 104:0:0 active
  buffer 31971493: fa48 size 276:0:0 active
  buffer 31971494: fb60 size 212:0:0 active
  buffer 31974327: fc38 size 28:8:0 active
  buffer 31971492: fd40 size 276:0:0 active
  buffer 31971604: fe58 size 152:0:0 active
  buffer 31972791: fef0 size 0:0:0 active
  buffer 31964212: fef8 size 152:0:0 active
  buffer 31974661: ff90 size 84:0:0 active
  buffer 31964283: ffe8 size 124:8:0 active
  buffer 31964399: 10070 size 152:0:0 active
  buffer 31971758: 10108 size 124:8:0 active
  buffer 31971893: 10190 size 152:0:0 active
  buffer 31971897: 10228 size 136:0:0 active
  buffer 31971898: 102b0 size 156:0:0 active
  buffer 31964470: 10360 size 124:8:0 active
  buffer 31971671: 103e8 size 196:0:0 active
  buffer 31964620: 104b0 size 416:40:0 active
  buffer 31964641: 10678 size 152:0:0 active
  buffer 31976272: 10710 size 108:8:0 active
  buffer 31964792: 10788 size 152:0:0 active
  buffer 31964866: 10820 size 240:0:0 active
  buffer 31975308: 10910 size 144:0:0 active
  buffer 31975481: 109a0 size 136:0:0 active
  buffer 31980964: 10a70 size 104:0:0 active
  buffer 31980976: 10ad8 size 104:0:0 active
  buffer 31980977: 10b40 size 104:0:0 active
  buffer 31980979: 10ba8 size 104:0:0 active
  buffer 31965154: 10c10 size 6800:120:0 active
  buffer 31980595: 12718 size 68:8:0 active
  buffer 31965339: 12770 size 152:0:0 active
  buffer 31975482: 12808 size 156:0:0 active
  buffer 31975511: 128a8 size 220:0:0 active
  buffer 31975512: 12988 size 164:0:0 active
  buffer 31975515: 12a30 size 124:0:0 active
  buffer 31975647: 12ab0 size 124:0:0 active
  buffer 31975917: 12b30 size 124:8:0 active
  buffer 31965471: 12bc0 size 392:24:0 active
  buffer 31965496: 12d60 size 6400:104:0 active
  buffer 31965519: 146c8 size 92:0:0 active
  buffer 31965941: 14728 size 240:0:0 active
  buffer 31965943: 14818 size 240:0:0 active
  buffer 31965949: 14908 size 240:0:0 active
  buffer 31965953: 149f8 size 240:0:0 active
  buffer 31965991: 14ae8 size 152:0:0 active
  buffer 31966000: 14b80 size 136:0:0 active
  buffer 31980987: 14c08 size 104:0:0 active
  buffer 31966094: 14ca8 size 124:0:0 active
  buffer 31966208: 14d28 size 152:0:0 active
  buffer 31966463: 14e38 size 152:0:0 active
  buffer 31966564: 14ed0 size 372:16:0 active
  buffer 31966599: 15058 size 6800:120:0 active
  buffer 31966673: 16b60 size 124:8:0 active
  buffer 31980783: 16be8 size 132:0:0 active
  buffer 31966745: 16cf0 size 152:0:0 active
  buffer 31966861: 16d88 size 208:0:0 active
  buffer 31967050: 16e58 size 152:0:0 active
  buffer 31967068: 16ef0 size 108:8:0 active
  buffer 31968154: 16f68 size 6004:88:0 active
  buffer 31968676: 18738 size 4396:64:0 active
  buffer 31974393: 198a8 size 124:8:0 active
  buffer 31974556: 19930 size 112:8:0 active
  buffer 31974576: 199a8 size 204:0:0 active
  buffer 31974577: 19a78 size 204:0:0 active
  buffer 31974589: 19b48 size 204:0:0 active
  buffer 31974590: 19c18 size 204:0:0 active
  buffer 31974599: 19ce8 size 240:0:0 active
  buffer 31974601: 19dd8 size 240:0:0 active
  buffer 31974603: 19ec8 size 240:0:0 active
  buffer 31974607: 19fb8 size 240:0:0 active
  buffer 31974624: 1a0a8 size 108:8:0 active
  buffer 31974662: 1a120 size 736:0:0 active
  buffer 31974663: 1a400 size 736:0:0 active
  buffer 31974667: 1a6e0 size 240:0:0 active
  buffer 31974671: 1a7d0 size 240:0:0 active
  buffer 31974676: 1a8c0 size 240:0:0 active
  buffer 31974678: 1a9b0 size 240:0:0 active
  buffer 31974771: 1aaa0 size 204:0:0 active
  buffer 31974772: 1ab70 size 204:0:0 active
  buffer 31974812: 1ac40 size 240:0:0 active
  buffer 31974814: 1ad30 size 240:0:0 active
  buffer 31974816: 1ae20 size 240:0:0 active
  buffer 31974820: 1af10 size 240:0:0 active
  buffer 31974825: 1b000 size 240:0:0 active
  buffer 31974827: 1b0f0 size 240:0:0 active
  buffer 31974906: 1b1e0 size 240:0:0 active
  buffer 31974910: 1b2d0 size 240:0:0 active
  buffer 31974919: 1b3c0 size 240:0:0 active
  buffer 31974930: 1b4b0 size 240:0:0 active
  buffer 31974936: 1b5a0 size 108:8:0 active
  buffer 31974942: 1b618 size 736:0:0 active
  buffer 31975005: 1b8f8 size 736:0:0 active
  buffer 31975018: 1bbd8 size 736:0:0 active
  buffer 31975019: 1beb8 size 736:0:0 active
  buffer 31975020: 1c198 size 752:0:0 active
  buffer 31975021: 1c488 size 204:0:0 active
  buffer 31975023: 1c558 size 240:0:0 active
  buffer 31975024: 1c648 size 204:0:0 active
  buffer 31975030: 1c718 size 240:0:0 active
  buffer 31975033: 1c808 size 240:0:0 active
  buffer 31975035: 1c8f8 size 240:0:0 active
  buffer 31975049: 1c9e8 size 240:0:0 active
  buffer 31975051: 1cad8 size 740:0:0 active
  buffer 31975057: 1cdc0 size 240:0:0 active
  buffer 31975062: 1ceb0 size 240:0:0 active
  buffer 31975067: 1cfa0 size 240:0:0 active
  buffer 31975124: 1d090 size 204:0:0 active
  buffer 31975126: 1d160 size 204:0:0 active
  buffer 31975131: 1d230 size 204:0:0 active
  buffer 31975132: 1d300 size 204:0:0 active
  buffer 31975136: 1d3d0 size 240:0:0 active
  buffer 31975141: 1d4c0 size 240:0:0 active
  buffer 31975143: 1d5b0 size 240:0:0 active
  buffer 31975146: 1d6a0 size 240:0:0 active
  buffer 31975181: 1d790 size 1380:0:0 active
  buffer 31975201: 1dcf8 size 736:0:0 active
  buffer 31975202: 1dfd8 size 736:0:0 active
  buffer 31975208: 1e2b8 size 240:0:0 active
  buffer 31975213: 1e3a8 size 240:0:0 active
  buffer 31975219: 1e498 size 240:0:0 active
  buffer 31975226: 1e588 size 240:0:0 active
  buffer 31975878: 1e678 size 224:0:0 active
  buffer 31976123: 1e758 size 144:0:0 active
  buffer 31976147: 1e7e8 size 204:0:0 active
  buffer 31976148: 1e8b8 size 204:0:0 active
  buffer 31976193: 1e988 size 204:0:0 active
  buffer 31976194: 1ea58 size 204:0:0 active
  buffer 31976206: 1eb28 size 240:0:0 active
  buffer 31976211: 1ec18 size 240:0:0 active
  buffer 31976287: 1ed08 size 364:8:0 active
  buffer 31976334: 1ee80 size 240:0:0 active
  buffer 31976415: 1ef70 size 736:0:0 active
  buffer 31976420: 1f250 size 736:0:0 active
  buffer 31976428: 1f530 size 240:0:0 active
  buffer 31976440: 1f620 size 240:0:0 active
  buffer 31976744: 1f710 size 112:8:0 active
  buffer 31976779: 1f788 size 112:8:0 active
  buffer 31976801: 1f800 size 536:32:0 active
  buffer 31976952: 1fa38 size 108:8:0 active
  buffer 31977172: 1fab0 size 108:8:0 active
  buffer 31977264: 1fb28 size 240:0:0 active
  buffer 31977266: 1fc18 size 240:0:0 active
  buffer 31977552: 1fd08 size 108:8:0 active
  buffer 31977574: 1fd80 size 188:40:0 active
  buffer 31977713: 1fe68 size 136:0:0 active
  buffer 31977714: 1fef0 size 156:0:0 active
  buffer 31977755: 1ff90 size 124:0:0 active
  buffer 31977798: 20010 size 108:8:0 active
  buffer 31977935: 20088 size 536:32:0 active
  buffer 31978097: 202c0 size 108:8:0 active
  buffer 31978367: 20338 size 108:8:0 active
  buffer 31978753: 203b0 size 108:8:0 active
  buffer 31978783: 20428 size 240:0:0 active
  buffer 31978828: 20518 size 112:8:0 active
  buffer 31978880: 20590 size 204:0:0 active
  buffer 31978881: 20660 size 204:0:0 active
  buffer 31978904: 20730 size 204:0:0 active
  buffer 31978905: 20800 size 204:0:0 active
  buffer 31978916: 208d0 size 240:0:0 active
  buffer 31978918: 209c0 size 240:0:0 active
  buffer 31978923: 20ab0 size 240:0:0 active
  buffer 31978927: 20ba0 size 240:0:0 active
  buffer 31978962: 20c90 size 204:0:0 active
  buffer 31978963: 20d60 size 204:0:0 active
  buffer 31979005: 20e30 size 204:0:0 active
  buffer 31979006: 20f00 size 204:0:0 active
  buffer 31979028: 20fd0 size 240:0:0 active
  buffer 31979032: 210c0 size 240:0:0 active
  buffer 31979035: 211b0 size 240:0:0 active
  buffer 31979042: 212a0 size 240:0:0 active
  buffer 31979083: 21390 size 204:0:0 active
  buffer 31979084: 21460 size 204:0:0 active
  buffer 31979100: 21530 size 108:8:0 active
  buffer 31979114: 215a8 size 204:0:0 active
  buffer 31979115: 21678 size 204:0:0 active
  buffer 31979121: 21748 size 240:0:0 active
  buffer 31979128: 21838 size 240:0:0 active
  buffer 31979134: 21928 size 240:0:0 active
  buffer 31979139: 21a18 size 240:0:0 active
  buffer 31979185: 21b08 size 736:0:0 active
  buffer 31979186: 21de8 size 736:0:0 active
  buffer 31979195: 220c8 size 240:0:0 active
  buffer 31979197: 221b8 size 240:0:0 active
  buffer 31979201: 222a8 size 240:0:0 active
  buffer 31979203: 22398 size 240:0:0 active
  buffer 31979254: 22488 size 204:0:0 active
  buffer 31979257: 22558 size 204:0:0 active
  buffer 31979299: 22628 size 204:0:0 active
  buffer 31979300: 226f8 size 204:0:0 active
  buffer 31979314: 227c8 size 240:0:0 active
  buffer 31979318: 228b8 size 240:0:0 active
  buffer 31979320: 229a8 size 240:0:0 active
  buffer 31979327: 22a98 size 240:0:0 active
  buffer 31979374: 22b88 size 736:0:0 active
  buffer 31979375: 22e68 size 736:0:0 active
  buffer 31979384: 23148 size 240:0:0 active
  buffer 31979386: 23238 size 240:0:0 active
  buffer 31979388: 23328 size 240:0:0 active
  buffer 31979390: 23418 size 240:0:0 active
  buffer 31979422: 23508 size 108:8:0 active
  buffer 31979470: 23580 size 240:0:0 active
  buffer 31979500: 23670 size 92:8:0 active
  buffer 31980458: 236d8 size 536:32:0 active
  buffer 31980630: 23910 size 108:8:0 active
  buffer 31980869: 23988 size 3960:56:0 active
  buffer 31980898: 24938 size 276:0:0 active
  buffer 31980899: 24a50 size 276:0:0 active
  buffer 31980901: 24b68 size 212:0:0 active
  buffer 31980902: 24c40 size 212:0:0 active
  buffer 31980900: 24d18 size 276:0:0 active
  buffer 31980903: 24e30 size 276:0:0 active
  pending transaction 837275575: 0000000000000000 from 19031:19159 to 2055:0 code 5f504944 flags 10 pri 0:100 r1 elapsed 57247ms node 7073 size 0:0 offset 36e0
  pending transaction 837275623: 0000000000000000 from 19530:19532 to 2055:0 code 5f444d50 flags 10 pri 0:100 r1 elapsed 57041ms node 7434 size 40:8 offset 4730
  node work 837274453: ub400007bfd9a81c0 cb400007d0ccb8df8
  pending transaction 837276056: 0000000000000000 from 2867:3799 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 54721ms node 7185 size 108:8 offset 3af8
  pending transaction 837276198: 0000000000000000 from 1316:1379 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 54095ms node 837276185 size 536:32 offset 2bf8
  pending transaction 837270459: 0000000000000000 from 1221:1221 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 72107ms node 7079 size 240:0 offset f8f0
  pending transaction 837276389: 0000000000000000 from 31835:3767 to 2055:0 code 15 flags 10 pri 0:120 r1 elapsed 53108ms node 6631 size 92:0 offset 23d8
  node work 837265262: ub400007bfd818ad0 cb400007c4cc2ccf0
  pending transaction 837276493: 0000000000000000 from 19031:19166 to 2055:0 code 5f504944 flags 10 pri 0:100 r1 elapsed 52799ms node 7434 size 0:0 offset 33d8
  pending transaction 837276626: 0000000000000000 from 19576:19578 to 2055:0 code 5f444d50 flags 10 pri 0:100 r1 elapsed 52028ms node 6695 size 40:8 offset 3678
  pending transaction 837273436: 0000000000000000 from 1197:1210 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 61619ms node 24506 size 108:8 offset 16ef0
  pending transaction 837276837: 0000000000000000 from 2923:10219 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 51093ms node 5847 size 104:0 offset 2eb8
  pending transaction 837276841: 0000000000000000 from 9106:22857 to 2055:0 code 1 flags 12 pri 0:120 r1 elapsed 51088ms node 5847 size 104:0 offset 2f20
  pending transaction 837276843: 0000000000000000 from 26486:19534 to 2055:0 code 1 flags 10 pri 0:130 r1 elapsed 51086ms node 5847 size 104:0 offset f548
  pending transaction 837276846: 0000000000000000 from 16834:24426 to 2055:0 code 1 flags 12 pri 0:120 r1 elapsed 51082ms node 5847 size 104:0 offset dfc8
  pending transaction 837276850: 0000000000000000 from 2576:13229 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 51078ms node 5847 size 104:0 offset e030
  pending transaction 837276849: 0000000000000000 from 16157:16589 to 2055:0 code 1 flags 12 pri 0:120 r1 elapsed 51078ms node 5847 size 104:0 offset e098
  pending transaction 837276854: 0000000000000000 from 12649:10373 to 2055:0 code 1 flags 10 pri 0:130 r1 elapsed 51072ms node 5847 size 104:0 offset e100
  pending transaction 837276947: 0000000000000000 from 19630:19630 to 2055:0 code 1a flags 12 pri 0:120 r1 elapsed 50435ms node 6656 size 112:8 offset f5b0
  node work 837276185: ub400007bfd82a680 cb400007d0cc9e958
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  pending transaction 837277045: 0000000000000000 from 1490:1490 to 2055:0 code 6 flags 10 pri 0:120 r1 elapsed 49956ms node 6656 size 140:8 offset f628
  node work 681109026: ub400007bfd17a520 cb400007c4cafb530
  node work 5335481: ub400007bfcc31610 cb400007c4cb65910
  node work 681109789: ub400007bfcf474e0 cb400007c4caa0330
  node work 681109857: ub400007bfcfbeac0 cb400007c4caca630
  pending transaction 837277083: 0000000000000000 from 1227:2341 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49810ms node 9472 size 204:0 offset f6c0
  pending transaction 837277114: 0000000000000000 from 1384:1399 to 2055:0 code 3 flags 11 pri 0:120 r0 elapsed 49672ms node 88742 size 384:0 offset b630
  pending transaction 837277132: 0000000000000000 from 1250:1271 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 49612ms node 7103 size 752:0 offset 3cc0
  pending transaction 837277324: 0000000000000000 from 3884:3884 to 2055:0 code 16 flags 10 pri 0:120 r1 elapsed 49257ms node 6656 size 312:0 offset eea0
  pending transaction 837277473: 0000000000000000 from 18571:18657 to 2055:0 code 36 flags 12 pri 0:120 r1 elapsed 48832ms node 6631 size 136:0 offset f860
  pending transaction 837277496: 0000000000000000 from 1500:18614 to 2055:0 code 1 flags 10 pri 0:130 r1 elapsed 48716ms node 6635 size 1256:0 offset bc38
  pending transaction 837277526: 0000000000000000 from 19687:19687 to 2055:0 code 5f434d44 flags 10 pri 0:120 r1 elapsed 48590ms node 6656 size 292:40 offset f2a8
  node work 836931327: ub400007bfd8a7b40 cb400007c4ced98f0
  node work 837164537: ub400007bfd709660 cb400007c4ccb1cb0
  node work 837165769: ub400007bfda54090 cb400007c4cb6c4b0
  node work 837166102: ub400007bfd980170 cb400007c4ccfcd10
  node work 837166229: ub400007bfdab8b30 cb400007c4cc75ad0
  node work 837170701: ub400007bfd4d14c0 cb400007c4cb26c10
  node work 837226738: ub400007bfd8e4bf0 cb400007c4cc19b50
  node work 837248528: ub400007bfd9d7f20 cb400007c4cdda530
  node work 837248584: ub400007bfd9dd200 cb400007c4cede6f0
  node work 837248951: ub400007bfda2fa60 cb400007c4cdf9d90
  node work 837250945: ub400007bfd93ece0 cb400007c4cd82b10
  pending transaction 837277820: 0000000000000000 from 18138:18157 to 2055:0 code 1 flags 12 pri 0:120 r1 elapsed 47167ms node 5847 size 104:0 offset f9e0
  pending transaction 837277860: 0000000000000000 from 2796:2862 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 47090ms node 26170 size 276:0 offset fd40
  pending transaction 837277861: 0000000000000000 from 2796:2862 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 47089ms node 26057 size 276:0 offset fa48
  pending transaction 837277862: 0000000000000000 from 2867:3542 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 47088ms node 49146 size 212:0 offset fb60
  pending transaction 837277863: 0000000000000000 from 2867:3542 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 47088ms node 49176 size 212:0 offset c688
  pending transaction 837277864: 0000000000000000 from 2867:2891 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 47088ms node 48886 size 276:0 offset c760
  pending transaction 837277865: 0000000000000000 from 2867:3270 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 47087ms node 48695 size 276:0 offset c878
  pending transaction 837277888: 0000000000000000 from 19711:19718 to 2055:0 code 5f444d50 flags 10 pri 0:100 r1 elapsed 47027ms node 7364 size 28:8 offset 2960
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has cleared dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has cleared dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  node work 837244174: ub400007bfd92e5d0 cb400007c4cdd2130
  node work 829451442: ub400007bfd95af70 cb400007c4cdc4990
  node work 830547045: ub400007bfd9d23a0 cb400007c4ce260d0
  node work 829649652: ub400007bfd94b2e0 cb400007c4ce14790
  node work 829451639: ub400007bfd8cc740 cb400007c4cce67b0
  node work 829651219: ub400007bfd80ec00 cb400007c4cb59f70
  node work 830547347: ub400007bfd93d900 cb400007c4cf1a390
  node work 837245089: ub400007bfda0bc10 cb400007c4cd5d070
  node work 830545996: ub400007bfd9b8c60 cb400007c4ce99870
  node work 837245437: ub400007bfdad1be0 cb400007c4cbeecb0
  node work 830546010: ub400007bfd9eb810 cb400007c4cea4370
  node work 836930860: ub400007bfdaf2af0 cb400007c4ce37a10
  node work 830546051: ub400007bfd9e0a40 cb400007c4cef8850
  node work 829740653: ub400007bfd556f90 cb400007c4cebe8f0
  node work 830546341: ub400007bfd9ab760 cb400007c4ce58830
  node work 830546456: ub400007bfd980a70 cb400007c4ceacef0
  node work 830546608: ub400007bfd973150 cb400007c4ce267f0
  node work 830546647: ub400007bfd926470 cb400007c4ce63b70
  node work 830546704: ub400007bfd9a9090 cb400007c4cee9910
  node work 830546705: ub400007bfd998200 cb400007c4ce45ff0
  node work 830745163: ub400007bfd946bd0 cb400007c4cfff650
  node work 830745317: ub400007bfd8b0ab0 cb400007c4cced230
  pending transaction 837274090: 0000000000000000 from 1197:1210 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 60117ms node 26208 size 108:8 offset 9370
  pending transaction 837278039: 0000000000000000 from 2867:3602 to 2055:0 code 2 flags 10 pri 0:120 r1 elapsed 46484ms node 5965 size 196:0 offset 103e8
  node work 837270037: ub400007bfd15eaa0 cb400007c4ca60730
  pending transaction 837278878: 0000000000000000 from 1316:1378 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 43027ms node 837278871 size 536:32 offset ccb8
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  node work 830840291: ub400007bfda34860 cb400007c4d000910
  node work 830840406: ub400007bfda0d950 cb400007c4cf6fd70
  node work 830840503: ub400007bfd99cb50 cb400007c4cffcad0
  node work 830840682: ub400007bfda37ec0 cb400007c4cfb4ad0
  node work 830841556: ub400007bfdaa0d40 cb400007c4cf75830
  node work 830859555: ub400007bfd7d6e30 cb400007c4ce75270
  node work 830844362: ub400007bfd346a80 cb400007c4cf234b0
  node work 830856913: ub400007bfda9b610 cb400007c4cfe58b0
  node work 830859588: ub400007bfd9316f0 cb400007c4ce99330
  node work 830861018: ub400007bfd5050c0 cb400007c4cb9ca50
  node work 830845183: ub400007bfd86fbf0 cb400007c4cc2f0f0
  node work 830845512: ub400007bfd82c060 cb400007c4cd51910
  node work 830875309: ub400007bfd91e730 cb400007c4cec4bf0
  node work 830845926: ub400007bfd8e6750 cb400007c4ccfac70
  node work 830857724: ub400007bfd90a9c0 cb400007c4cf50690
  node work 830857896: ub400007bfdab7780 cb400007c4cfe4cb0
  node work 837164564: ub400007bfd7e70f0 cb400007c4cc7d510
  node work 830858357: ub400007bfdae0580 cb400007c4cf610d0
  node work 830846129: ub400007bfd876370 cb400007c4cd5f6b0
  node work 830860066: ub400007bfd209080 cb400007c4cf2cbd0
  node work 831376342: ub400007bfd6b0020 cb400007c4cc85af0
  node work 830860233: ub400007bfd3814f0 cb400007c4cfa31f0
  node work 830860601: ub400007bfd3e7b80 cb400007c4ca25870
  node work 830860981: ub400007bfd596950 cb400007c4cbb4990
  node work 837222132: ub400007bfd708040 cb400007c4ccdd870
  node work 837248595: ub400007bfd96fca0 cb400007c4ce121b0
  node work 831507972: ub400007bfda3d860 cb400007c4ce5b110
  node work 830871533: ub400007bfd8095c0 cb400007c4ce9ea90
  node work 830863428: ub400007bfd851110 cb400007c4cd85210
  node work 830863859: ub400007bfccd14b0 cb400007c4cad37b0
  node work 830863861: ub400007bfcfd7ed0 cb400007c4cb8bf50
  node work 830864093: ub400007bfd81fa60 cb400007c4cd17cb0
  node work 830850189: ub400007bfd98e810 cb400007c4cf12b90
  node work 830850436: ub400007bfd997420 cb400007c4cfc5270
  node work 830850500: ub400007bfd99d720 cb400007c4cfb6270
  node work 830850611: ub400007bfd9c9760 cb400007c4cf691d0
  node work 830876509: ub400007bfdae7e70 cb400007c4ce9d5f0
  node work 830850773: ub400007bfd98b1b0 cb400007c4cf20bd0
  node work 830850909: ub400007bfd956950 cb400007c4cf69590
  node work 831478451: ub400007bfd91ba60 cb400007c4ce62010
  node work 830851236: ub400007bfd99d0c0 cb400007c4cfc0110
  node work 830851316: ub400007bfd9be120 cb400007c4cf8baf0
  node work 830851345: ub400007bfd9e7df0 cb400007c4cff4d30
  node work 830851382: ub400007bfd97d170 cb400007c4cf95750
  node work 830851595: ub400007bfd971d40 cb400007c4cf22250
  node work 830851637: ub400007bfd99c760 cb400007c4cfda210
  node work 830851765: ub400007bfd9ade90 cb400007c4cfc9a10
  node work 830851787: ub400007bfd882dc0 cb400007c4cf6ea50
  node work 830852160: ub400007bfd9c2530 cb400007c4cfabb90
  node work 830852346: ub400007bfd991f60 cb400007c4cff68f0
  node work 830852395: ub400007bfd98dc70 cb400007c4cff3ad0
  node work 830852438: ub400007bfd857b90 cb400007c4cfb4410
  node work 830852461: ub400007bfd882e20 cb400007c4cfec0f0
  node work 830852477: ub400007bfd997960 cb400007c4cf728f0
  node work 830852518: ub400007bfd990eb0 cb400007c4cfc9f50
  node work 830852539: ub400007bfd637ed0 cb400007c4cf5b070
  node work 830852563: ub400007bfd92ac70 cb400007c4cf5de90
  node work 830852638: ub400007bfd9dab30 cb400007c4cfd5b90
  node work 830852717: ub400007bfd9e1640 cb400007c4cf8ebb0
  node work 830852886: ub400007bfd9a8580 cb400007c4cfbba90
  node work 830853014: ub400007bfd96f1f0 cb400007c4cf4b2f0
  node work 830853098: ub400007bfd887950 cb400007c4cf60950
  node work 830853164: ub400007bfd918b50 cb400007c4cf68c30
  node work 830853220: ub400007bfd968bf0 cb400007c4cfeba90
  node work 830853250: ub400007bfd9b88d0 cb400007c4cf9d9d0
  node work 830853279: ub400007bfd93fb20 cb400007c4cf34910
  node work 830853311: ub400007bfd9bc290 cb400007c4cfad930
  node work 830853364: ub400007bfd9680e0 cb400007c4cf51b30
  node work 830853403: ub400007bfd9b2a20 cb400007c4cf27cb0
  node work 830853482: ub400007bfd95c740 cb400007c4cfe94b0
  node work 830853553: ub400007bfd9785e0 cb400007c4cf7fdf0
  node work 830853595: ub400007bfd98cb90 cb400007c4cf2e0d0
  node work 830853598: ub400007bfd97e9d0 cb400007c4cf23a50
  node work 830853611: ub400007bfd98e0f0 cb400007c4cfdfc10
  node work 835977273: ub400007bfd943480 cb400007c9cb67058
  node work 830855741: ub400007bfdac9870 cb400007c4cf4bfb0
  pending transaction 837279080: 0000000000000000 from 19789:19791 to 2055:0 code 5f444d50 flags 10 pri 0:100 r1 elapsed 42019ms node 6666 size 28:8 offset 98f0
  has dead binder
  pending transaction 837279091: 0000000000000000 from 2576:2669 to 2055:0 code 16 flags 10 pri 0:120 r1 elapsed 41963ms node 11810 size 120:0 offset cf88
  pending transaction 837279120: 0000000000000000 from 30854:30889 to 2055:0 code 15 flags 12 pri 0:129 r1 elapsed 41784ms node 7973 size 100:0 offset bb30
  pending transaction 837279159: 0000000000000000 from 16057:16675 to 2055:0 code 5f4e5446 flags 10 pri 0:130 r1 elapsed 41505ms node 3933 size 0:0 offset fef0
  pending transaction 837279338: 0000000000000000 from 19804:19804 to 2055:0 code 1a flags 12 pri 0:120 r1 elapsed 40389ms node 6656 size 112:8 offset d1b8
  pending transaction 837279433: 0000000000000000 from 19821:19822 to 2055:0 code 5f444d50 flags 10 pri 0:120 r1 elapsed 39779ms node 7364 size 28:8 offset 1668
  node work 837278871: ub400007bfd819400 cb400007d0ccf6a68
  pending transaction 837279621: 0000000000000000 from 16834:16834 to 2055:0 code 2 flags 12 pri 0:120 r1 elapsed 38961ms node 7364 size 96:0 offset d430
  pending transaction 837279623: 0000000000000000 from 25802:25802 to 2055:0 code 2 flags 12 pri 0:120 r1 elapsed 38960ms node 7364 size 96:0 offset d490
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  node work 832624992: ub400007bfd9bcb60 cb400007c4ce22830
  node work 832625164: ub400007bfd2cc9b0 cb400007c4cd137b0
  node work 53397: ub400007bfcf47c00 cb400007c4cafcdf0
  pending transaction 837279779: 0000000000000000 from 16057:16105 to 2055:0 code 15 flags 12 pri 0:129 r1 elapsed 37915ms node 7973 size 100:0 offset d768
  pending transaction 837279782: 0000000000000000 from 25802:31934 to 2055:0 code 15 flags 12 pri 0:129 r1 elapsed 37914ms node 7973 size 100:0 offset d7d0
  pending transaction 837279812: 0000000000000000 from 16157:16378 to 2055:0 code 3 flags 12 pri 0:129 r1 elapsed 37733ms node 6631 size 144:0 offset d838
  pending transaction 837279948: 0000000000000000 from 19845:19847 to 2055:0 code 5f444d50 flags 10 pri 0:100 r1 elapsed 36891ms node 5847 size 28:8 offset 3240
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  node work 835340376: ub400007bfd8eda70 cb400007c4ca892f0
  node work 835340424: ub400007bfd80f140 cb400007c4cc377f0
  node work 835340848: ub400007bfd948d90 cb400007c4cd41410
  node work 835341035: ub400007bfd944cb0 cb400007c3ce43990
  node work 542628557: ub400007bfd014350 cb400007c4cecc930
  pending transaction 837280695: 0000000000000000 from 19853:19854 to 2055:0 code 5f444d50 flags 10 pri 0:100 r1 elapsed 31870ms node 13989 size 28:8 offset fc38
  pending transaction 837280924: 0000000000000000 from 19855:19855 to 2055:0 code 1a flags 12 pri 0:120 r1 elapsed 30293ms node 6656 size 112:8 offset 19930
  pending transaction 837281029: 0000000000000000 from 11192:11221 to 2055:0 code 1 flags 12 pri 0:120 r1 elapsed 29761ms node 8071 size 84:0 offset ff90
  pending transaction 837281073: 0000000000000000 from 19873:19874 to 2055:0 code 5f444d50 flags 10 pri 0:120 r1 elapsed 29673ms node 7344 size 28:8 offset 7a38
  pending transaction 837281152: 0000000000000000 from 19875:19877 to 2055:0 code 5f444d50 flags 10 pri 0:120 r1 elapsed 29139ms node 7364 size 28:8 offset 2f88
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  node work 837129503: ub400007bfd9b9140 cb400007c4cde8390
  node work 835724040: ub400007bfd842f50 cb400007c4cff6b30
  node work 835732897: ub400007bfd9d6240 cb400007c4cec8730
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  node work 836986536: ub400007bfd8006b0 cb400007c4cdf80b0
  node work 837237123: ub400007bfd945070 cb400007c4cd1c630
  node work 836986879: ub400007bfd9e6380 cb400007c4ce874b0
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  node work 836669125: ub400007bfd98eae0 cb400007c4ce7e150
  node work 34461: ub400007bfcc17900 cb400007c4ca886f0
  node work 836674099: ub400007bfd9edcd0 cb400007c4ce10e30
  node work 836889635: ub400007bfd922d80 cb400007c4ced74f0
  pending transaction 837281349: 0000000000000000 from 4973:5989 to 2055:0 code 3 flags 12 pri 0:120 r1 elapsed 28256ms node 8071 size 84:0 offset 26e0
  pending transaction 837275180: 0000000000000000 from 1197:1210 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 58617ms node 24687 size 108:8 offset 3c48
  pending transaction 837281676: 0000000000000000 from 1490:2174 to 2055:0 code 1 flags 10 pri 0:100 r1 elapsed 26854ms node 6705 size 144:0 offset 10910
  pending transaction 837275604: 0000000000000000 from 1197:1210 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 57116ms node 24586 size 108:8 offset 3970
  pending transaction 837281880: 0000000000000000 from 1195:19901 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 25434ms node 21146 size 164:0 offset 12988
  pending transaction 837282052: 0000000000000000 from 19909:19912 to 2055:0 code 5f444d50 flags 10 pri 0:100 r1 elapsed 24166ms node 8000 size 48:8 offset 3c08
  pending transaction 837282164: 0000000000000000 from 19939:19940 to 2055:0 code 5f444d50 flags 10 pri 0:100 r1 elapsed 23688ms node 5620 size 40:8 offset 1f18
  pending transaction 837282246: 0000000000000000 from 2796:2796 to 2055:0 code 20 flags 12 pri 0:120 r1 elapsed 23273ms node 6631 size 224:0 offset 1e678
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  node work 827757269: ub400007bfd975ee0 cb400007c4cd0a4b0
  node work 827757878: ub400007bfd903dc0 cb400007c4cd52c30
  node work 827758279: ub400007bfd98ed80 cb400007c4cda78f0
  pending transaction 837282491: 0000000000000000 from 1499:1499 to 2055:0 code 1 flags 10 pri 0:100 r1 elapsed 21787ms node 6705 size 144:0 offset 1e758
  pending transaction 837282655: 0000000000000000 from 2576:2771 to 2055:0 code 15 flags 10 pri 0:120 r1 elapsed 21050ms node 18440 size 364:8 offset 1ed08
  node work 835536014: ub400007bfd93ceb0 cb400007c4ce2fa90
  node work 836931370: ub400007bfd8b49e0 cb400007c4cecd050
  node work 836964079: ub400007bfd937c30 cb400007c4ce43950
  node work 837108059: ub400007bfd50a5b0 cb400007c4cb87b70
  has dead binder
  pending transaction 837283112: 0000000000000000 from 19967:19967 to 2055:0 code 1a flags 12 pri 0:120 r1 elapsed 20296ms node 6656 size 112:8 offset 1f710
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  node work 835436870: ub400007bfd9d9870 cb400007c4cdb2b10
  node work 837214441: ub400007bfd825af0 cb400007c4cd9d0f0
  node work 837239634: ub400007bfd9245b0 cb400007c4cd323b0
  node work 837252094: ub400007bfd9c96d0 cb400007c4cdfc1f0
  node work 837278029: ub400007bfd985c00 cb400007c4cada950
  node work 836677112: ub400007bfd957e80 cb400007c4ce612f0
  node work 835470398: ub400007bfd9e6710 cb400007c4ce10ef0
  pending transaction 837283147: 0000000000000000 from 19987:19987 to 2055:0 code 1a flags 12 pri 0:120 r1 elapsed 20136ms node 6656 size 112:8 offset 1f788
  pending transaction 837283169: 0000000000000000 from 1316:1378 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 20061ms node 837283160 size 536:32 offset 1f800
  pending transaction 837283406: 0000000000000000 from 20028:20029 to 2055:0 code 5f444d50 flags 10 pri 0:120 r1 elapsed 19080ms node 7344 size 28:8 offset 4a88
  pending transaction 837283631: 0000000000000000 from 20035:20036 to 2055:0 code 5f444d50 flags 10 pri 0:120 r1 elapsed 17877ms node 6673 size 28:8 offset 39e8
  pending transaction 837283801: 0000000000000000 from 1494:20041 to 2055:0 code 5f444d50 flags 10 pri 0:120 r1 elapsed 16944ms node 3917 size 64:8 offset de70
  pending transaction 837283942: 0000000000000000 from 20048:20048 to 2055:0 code 5f434d44 flags 10 pri 0:100 r1 elapsed 16472ms node 7434 size 188:40 offset 1fd80
  node work 837283160: ub400007bfdb40100 cb400007d0cdc7b18
  pending transaction 837284303: 0000000000000000 from 1316:1378 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 14297ms node 837284295 size 536:32 offset 20088
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  has dead binder
  node work 836576328: ub400007bfd5b3900 cb400007c4ccbb8b0
  node work 836679008: ub400007bfd962a70 cb400007c4ce54f30
  node work 27996: ub400007bfcb0b400 cb400007c4cadf930
  node work 837284295: ub400007bfdb41450 cb400007d0cd86c58
  pending transaction 837285196: 0000000000000000 from 20100:20100 to 2055:0 code 1a flags 12 pri 0:120 r1 elapsed 10228ms node 6656 size 112:8 offset 20518
  pending transaction 837285868: 0000000000000000 from 20141:20142 to 2055:0 code 5f444d50 flags 10 pri 0:100 r1 elapsed 7177ms node 6656 size 92:8 offset 23670
  pending transaction 837286011: 0000000000000000 from 2885:4133 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 6814ms node 5798 size 212:8 offset 4888
  pending transaction 837286116: 0000000000000000 from 1316:1378 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 6221ms node 837286110 size 536:32 offset 4b68
  pending transaction 837286396: 0000000000000000 from 20184:20185 to 2055:0 code 5f444d50 flags 10 pri 0:100 r1 elapsed 4689ms node 6656 size 28:8 offset 2280
  node work 837286110: ub400007bfda2ecb0 cb400007d0cc2c0d8
  pending transaction 837286826: 0000000000000000 from 1316:1378 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 2104ms node 837286817 size 536:32 offset 236d8
  pending transaction 837286963: 0000000000000000 from 20273:20274 to 2055:0 code 5f444d50 flags 10 pri 0:100 r1 elapsed 1547ms node 8071 size 68:8 offset 12718
  pending transaction 837287151: 0000000000000000 from 2867:2891 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 867ms node 837287149 size 132:0 offset 16be8
  pending transaction 837287156: 0000000000000000 from 3796:5922 to 2055:0 code 1 flags 12 pri 0:120 r1 elapsed 862ms node 837287153 size 132:0 offset 86d0
  pending transaction 837287165: 0000000000000000 from 29399:29506 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 846ms node 837287161 size 132:0 offset 8758
  node work 793516495: ub400007bfd8eb400 cb400007c3cf94350
  node work 676845155: ub400007bfd343c00 cb400007c4ce21a50
  node work 676751254: ub400007bfd415120 cb400007c3cb64250
  node work 676757066: ub400007bfd5eda40 cb400007c3cb4a210
  pending transaction 837269536: 0000000000000000 from 1490:29079 to 2055:0 code 5 flags 11 pri 0:120 r0 elapsed 74081ms node 7686 size 96:0 offset 9658
  pending transaction 837271839: 0000000000000000 from 1316:1757 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 67226ms node 42347 size 392:24 offset 12bc0
  pending transaction 837271522: 0000000000000000 from 1316:2260 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 68423ms node 7352 size 6800:120 offset 10c10
  node work 676751143: ub400007bfd34bd30 cb400007c3cb1bbd0
  pending transaction 837287300: 0000000000000000 from 2712:2712 to 2055:0 code 1 flags 12 pri 0:120 r1 elapsed 508ms node 5847 size 104:0 offset 5660
  pending transaction 837287302: 0000000000000000 from 4937:6786 to 2055:0 code 1 flags 12 pri 0:120 r1 elapsed 506ms node 5847 size 104:0 offset 3268
  pending transaction 837287306: 0000000000000000 from 2867:4023 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 498ms node 5847 size 104:0 offset 22a8
  pending transaction 837287307: 0000000000000000 from 2885:24824 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 496ms node 5847 size 104:0 offset 87e0
  pending transaction 837287316: 0000000000000000 from 2867:3938 to 2055:0 code 22 flags 10 pri 0:120 r1 elapsed 475ms node 31598 size 152:0 offset 7a60
  pending transaction 837287330: 0000000000000000 from 12066:6778 to 2055:0 code 1 flags 12 pri 0:120 r1 elapsed 446ms node 5847 size 104:0 offset 7af8
  pending transaction 837287332: 0000000000000000 from 12591:12591 to 2055:0 code 1 flags 12 pri 0:120 r1 elapsed 445ms node 5847 size 104:0 offset 10a70
  pending transaction 837287344: 0000000000000000 from 18571:18666 to 2055:0 code 1 flags 12 pri 0:120 r1 elapsed 440ms node 5847 size 104:0 offset 10ad8
  pending transaction 837287345: 0000000000000000 from 29399:29399 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 440ms node 5847 size 104:0 offset 10b40
  pending transaction 837287346: 0000000000000000 from 18552:18648 to 2055:0 code 3 flags 12 pri 0:120 r1 elapsed 438ms node 57608 size 156:0 offset 9490
  pending transaction 837287347: 0000000000000000 from 16454:15526 to 2055:0 code 1 flags 12 pri 0:120 r1 elapsed 438ms node 5847 size 104:0 offset 10ba8
  pending transaction 837287350: 0000000000000000 from 18107:18272 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 437ms node 5847 size 104:0 offset 9530
  pending transaction 837272368: 0000000000000000 from 1195:1204 to 2055:0 code 5 flags 11 pri 0:120 r0 elapsed 65675ms node 14040 size 136:0 offset 14b80
  pending transaction 837287351: 0000000000000000 from 14237:12322 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 434ms node 5847 size 104:0 offset 9598
  pending transaction 837287352: 0000000000000000 from 25802:32098 to 2055:0 code 1 flags 12 pri 0:120 r1 elapsed 433ms node 5847 size 104:0 offset 8648
  pending transaction 837275847: 0000000000000000 from 1195:1204 to 2055:0 code 2 flags 11 pri 0:120 r0 elapsed 55672ms node 7969 size 156:0 offset 3a58
  pending transaction 837287354: 0000000000000000 from 29399:29496 to 2055:0 code 56 flags 10 pri 0:120 r1 elapsed 425ms node 7364 size 248:8 offset 7c48
  pending transaction 837287355: 0000000000000000 from 11690:11999 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 425ms node 5847 size 104:0 offset 14c08
  pending transaction 837276180: 0000000000000000 from 1197:1210 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 54114ms node 24515 size 108:8 offset 27b8
  pending transaction 837287365: 0000000000000000 from 1302:29481 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 411ms node 5624 size 144:0 offset 84c8
  pending transaction 837287367: 0000000000000000 from 1302:16165 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 410ms node 5624 size 152:0 offset 8558
  pending transaction 837287363: 0000000000000000 from 1302:6488 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 412ms node 5624 size 152:0 offset 8390
  pending transaction 837287369: 0000000000000000 from 1302:5814 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 408ms node 5624 size 152:0 offset 8848
  has dead binder
  pending transaction 837287400: 0000000000000000 from 1302:16166 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 389ms node 5624 size 152:0 offset 82f8
  pending transaction 837287401: 0000000000000000 from 1302:1302 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 388ms node 5624 size 152:0 offset 30b0
  pending transaction 837287403: 0000000000000000 from 1302:1421 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 387ms node 5624 size 152:0 offset 8d90
  pending transaction 837287407: 0000000000000000 from 1302:1373 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 384ms node 5624 size 152:0 offset 90b8
  pending transaction 837287412: 0000000000000000 from 1302:29202 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 382ms node 5624 size 172:0 offset 9150
  pending transaction 837287416: 0000000000000000 from 1302:9266 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 382ms node 5624 size 152:0 offset 8e28
  pending transaction 837287417: 0000000000000000 from 1302:29480 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 381ms node 5624 size 152:0 offset 8ec0
  pending transaction 837287418: 0000000000000000 from 1302:29271 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 375ms node 5624 size 172:0 offset 8f58
  pending transaction 837287419: 0000000000000000 from 1302:16164 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 374ms node 5624 size 152:0 offset 88e0
  pending transaction 837287420: 0000000000000000 from 1302:3298 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 374ms node 5624 size 152:0 offset 8978
  pending transaction 837287429: 0000000000000000 from 1302:7203 to 2055:0 code 6 flags 10 pri 0:120 r1 elapsed 365ms node 5624 size 124:8 offset 8a10
  pending transaction 837287431: 0000000000000000 from 1302:29479 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 354ms node 5624 size 152:0 offset 9008
  pending transaction 837287436: 0000000000000000 from 1302:1372 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 345ms node 5624 size 152:0 offset 9200
  pending transaction 837273229: 0000000000000000 from 1316:1316 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 62248ms node 11143 size 208:0 offset 16d88
  pending transaction 837276521: 0000000000000000 from 1197:1210 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 52614ms node 24524 size 108:8 offset 4760
  pending transaction 837287499: 0000000000000000 from 2867:3784 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 140ms node 5798 size 208:8 offset 9298
  pending transaction 837275856: 0000000000000000 from 1197:1210 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 55616ms node 26205 size 108:8 offset 3360
  pending transaction 837267928: 0000000000000000 from 1247:1277 to 2055:0 code 1 flags 11 pri 0:120 r0 elapsed 77764ms node 17240 size 152:0 offset 4ad0
  pending transaction 837287556: 0000000000000000 from 20292:20312 to 2055:0 code 5f444d50 flags 10 pri 0:120 r1 elapsed 81ms node 6673 size 28:8 offset 2310
  pending transaction 837287576: 0000000000000000 from 16057:16057 to 2055:0 code 4a flags 12 pri 0:120 r1 elapsed 75ms node 6656 size 444:8 offset 96b8
  pending transaction 837287580: 0000000000000000 from 18107:18107 to 2055:0 code 2 flags 10 pri 0:120 r1 elapsed 73ms node 837275175 size 112:0 offset 9880
  node work 837275202: ub400007bfca04660 cb400007c3ca25150
  node work 837287569: ub400007bfd991f90 cb400007c4caeee10
  pending transaction 837287597: 0000000000000000 from 2576:2616 to 2055:0 code b flags 10 pri 0:130 r1 elapsed 62ms node 8000 size 88:0 offset 9600
  pending transaction 837287600: 0000000000000000 from 2576:2607 to 2055:0 code 24 flags 10 pri 0:118 r1 elapsed 58ms node 17783 size 112:0 offset 2210
  pending transaction 837287605: 0000000000000000 from 2867:2867 to 2055:0 code 22 flags 10 pri 0:120 r1 elapsed 45ms node 6631 size 228:0 offset 6d20
  pending transaction 837287606: 0000000000000000 from 2867:3995 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 38ms node 5798 size 304:8 offset b420
  pending transaction 837287612: 0000000000000000 from 5153:5194 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 27ms node 3933 size 96:0 offset 21b0
```


这部分 `system_server` (2055) 的日志简直是“灾难现场”的特写。它不仅印证了我们之前的推断，还揭示了一个更深层的系统级问题：**全系统异步事务大爆炸**。

通过这段日志，我们可以总结出三个极其危险的信号：

### 1. `system_server` 线程池彻底枯竭

看这一排排的线程（2078, 2079, 2215, 2227...）：

* **状态**：几乎所有线程都卡在 `incoming transaction`。
* **耗时（Elapsed）**：注意那些天文数字（如 `408774060ms`）。这通常是由于内核时间戳溢出或极其严重的逻辑卡死。
* **Code `5f434d44**`：这是一个非常有名的特征码，它其实是 ASCII 码的 **"_CMD"**。这通常对应 `system_server` 内部用于调试、dump 或特定系统指令的 Binder 调用。
* **结论**：`system_server` 的 31 个（或更多）Binder 线程已经全部被占满，且无法释放。现在的 `system_server` 已经无法处理任何新的请求，哪怕是简单的 `ping`。

---

### 2. “死亡队列”：惊人的 Pending 堆积

你提供的 `node` 节点信息揭示了谁在“狂炸” `system_server`：

* **Node 9472 (来自 proc 1227)**：堆积了 **30+ 条** `pending async transaction`。
* **Node 7079 (来自 proc 1221)**：堆积了 **50+ 条**（甚至更多）`pending async transaction`。
* **特征**：几乎全是 `code 1` 且 `flags 11` (oneway)。
* **解读**：进程 1227 和 1221 正疯狂向 `system_server` 发送异步消息。由于 `system_server` 已经没有线程可以处理这些消息，它们全堆在了内核缓冲区里。

---

### 3. 关键嫌疑人：进程 2867 和 1316

在线程 2055 和 3266 中，我们看到了 `outgoing` 指向了 **2867**：

* **线程 2055 (主线程/核心线程)**：正试图联络 2867，`elapsed 6712ms`。
* **线程 3266**：也在联络 2867，`elapsed 57492ms`。
* **结论**：**2867 是这一连串卡死的底层诱因。** `system_server` 持有某些锁（可能就是 AMS 锁）去联络 2867，但 2867 不回话，导致锁不释放。

再看 **Node 7352 (来自 proc 1316)**：

* 它发送了 `size 6400`、`6800` 的大数据块。在 Binder 中，单次发送超过 4KB 已经算大的了。这种频繁的大数据异步投递极易瞬间耗尽 `system_server` 的 1MB 共享缓冲区。

---

### 综合判案报告

**这是一场由底向上触发的“全系统雪崩”：**

1. **根源层 (2867)**：疑似某个硬件服务（HAL）或底层守护进程挂起，不回 `system_server` 的消息（code `db`, `bd`）。
2. **锁死层 (system_server)**：`system_server` 为了等 2867，持有了关键全局锁（AMS/WMS），导致所有试图进入 `system_server` 的请求（来自 18571, 31727 等）全部在门口排队。
3. **爆发层 (1221/1227/1316)**：由于系统卡顿，这些进程（可能是 SensorService 或 Input 相关的）触发了大量重试或高频状态更新（code 1），瞬间填满了内核缓冲区。
4. **结局**：`system_server` 线程耗尽 + 缓冲区耗尽，Watchdog 最终超时触发重启。

---

### 最后的排查建议

* **查进程 2867**：请务必告诉我 `ps -A | grep 2867` 的结果。我怀疑它是 **`android.hardware.xxx`** 相关的进程（比如 Camera 或 Sensor）。
* **查进程 1316**：这个发大数据的家伙也很有嫌疑。

**你想让我帮你分析 2867 的身份以及那些 `5f434d44` (_CMD) 事务到底是谁发过来的吗？这能定位到是哪个调试工具或异常监控导致了二次伤害。**

---
![img_2.png](img_2.png)

```
proc 2867
context binder
  thread 2867: l 10 need_return 0 tr 0
    outgoing transaction 837287605: 0000000000000000 from 2867:2867 to 2055:0 code 22 flags 10 pri 0:120 r1 elapsed 39ms
    transaction complete
  thread 2891: l 11 need_return 0 tr 0
    outgoing transaction 837287151: 0000000000000000 from 2867:2891 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 862ms
    transaction complete
  thread 3262: l 01 need_return 0 tr 0
    incoming transaction 837275541: 0000000000000000 from 2055:3266 to 2867:3262 code bd flags 10 pri 0:120 r1 elapsed 57488ms node 52399 size 104:0 offset 4440
  thread 3270: l 01 need_return 0 tr 0
    incoming transaction 837286038: 0000000000000000 from 2055:2055 to 2867:3270 code db flags 10 pri 0:118 r1 elapsed 6708ms node 52399 size 112:0 offset 108f0
  thread 3343: l 01 need_return 0 tr 0
    incoming transaction 837269964: 0000000000000000 from 2923:3137 to 2867:3343 code 45 flags 10 pri 0:120 r1 elapsed 73283ms node 52399 size 104:0 offset 200
  thread 3602: l 10 need_return 0 tr 0
    outgoing transaction 837278039: 0000000000000000 from 2867:3602 to 2055:0 code 2 flags 10 pri 0:120 r1 elapsed 46479ms
    transaction complete
  thread 3784: l 11 need_return 0 tr 0
    outgoing transaction 837287499: 0000000000000000 from 2867:3784 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 134ms
    transaction complete
  thread 3799: l 11 need_return 0 tr 0
    outgoing transaction 837276056: 0000000000000000 from 2867:3799 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 54716ms
    incoming transaction 837276055: 0000000000000000 from 16412:16477 to 2867:3799 code 7 flags 12 pri 0:120 r1 elapsed 54716ms node 837266712 size 72:0 offset 318
  thread 3938: l 10 need_return 0 tr 0
    outgoing transaction 837287316: 0000000000000000 from 2867:3938 to 2055:0 code 22 flags 10 pri 0:120 r1 elapsed 470ms
    transaction complete
  thread 3995: l 10 need_return 0 tr 0
    outgoing transaction 837287606: 0000000000000000 from 2867:3995 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 32ms
    transaction complete
  thread 4023: l 10 need_return 0 tr 0
    outgoing transaction 837287306: 0000000000000000 from 2867:4023 to 2055:0 code 1 flags 10 pri 0:120 r1 elapsed 492ms
    transaction complete
  thread 4076: l 01 need_return 0 tr 0
    incoming transaction 837271899: 0000000000000000 from 2885:2885 to 2867:4076 code 29 flags 10 pri 0:120 r1 elapsed 67177ms node 52399 size 104:0 offset 44b8
  node 676995385: ub400007bfca3c6a0 cb400007c4ca6f4f0 pri 0:139 hs 1 hw 1 ls 4 lw 0 is 1 iw 1 tr 1 proc 7355
    pending async transaction 837269856: 0000000000000000 from 7355:7384 to 2867:0 code 7 flags 11 pri 0:120 r0 elapsed 73568ms node 676995385 size 176:0 offset 150
    pending async transaction 837275191: 0000000000000000 from 7355:7384 to 2867:0 code 7 flags 11 pri 0:120 r0 elapsed 58604ms node 676995385 size 176:0 offset 268
    pending async transaction 837287613: 0000000000000000 from 7355:7384 to 2867:0 code 7 flags 11 pri 0:120 r0 elapsed 17ms node 676995385 size 176:0 offset 6c8
  node 44862: ub400007bfca41fb0 cb400007c4ca251b0 pri 0:139 hs 1 hw 1 ls 10 lw 0 is 1 iw 1 tr 1 proc 2055
    pending async transaction 837271290: 0000000000000000 from 2055:2093 to 2867:0 code 1 flags 11 pri 0:120 r0 elapsed 68612ms node 44862 size 124:0 offset 4178
    pending async transaction 837271574: 0000000000000000 from 2055:2093 to 2867:0 code 1 flags 11 pri 0:120 r0 elapsed 68382ms node 44862 size 124:0 offset 4338
    pending async transaction 837271981: 0000000000000000 from 2055:2093 to 2867:0 code 1 flags 11 pri 0:120 r0 elapsed 67145ms node 44862 size 124:0 offset 4520
    pending async transaction 837272943: 0000000000000000 from 2055:2093 to 2867:0 code 1 flags 11 pri 0:120 r0 elapsed 63602ms node 44862 size 124:0 offset 6e70
    pending async transaction 837274955: 0000000000000000 from 2055:2093 to 2867:0 code 1 flags 11 pri 0:120 r0 elapsed 58874ms node 44862 size 124:0 offset 97a0
    pending async transaction 837279567: 0000000000000000 from 2055:2093 to 2867:0 code 1 flags 11 pri 0:120 r0 elapsed 39002ms node 44862 size 124:0 offset a698
    pending async transaction 837282669: 0000000000000000 from 2055:2093 to 2867:0 code 1 flags 11 pri 0:120 r0 elapsed 21026ms node 44862 size 124:0 offset cf40
    pending async transaction 837285140: 0000000000000000 from 2055:2093 to 2867:0 code 1 flags 11 pri 0:120 r0 elapsed 10263ms node 44862 size 124:0 offset 10768
    pending async transaction 837285871: 0000000000000000 from 2055:2093 to 2867:0 code 1 flags 11 pri 0:120 r0 elapsed 7171ms node 44862 size 124:0 offset 10870
  node 65385: ub400007bfca57430 cb400007c4ca2d790 pri 0:139 hs 1 hw 1 ls 1 lw 0 is 1 iw 1 tr 1 proc 2055
  node 676995229: ub400007bfca5ce60 cb400007c4ca64ab0 pri 0:139 hs 1 hw 1 ls 100 lw 0 is 1 iw 1 tr 1 proc 7355
    pending async transaction 837267884: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 77856ms node 676995229 size 320:0 offset 898
    pending async transaction 837267959: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 77681ms node 676995229 size 320:0 offset c68
    pending async transaction 837268489: 0000000000000000 from 7355:7384 to 2867:0 code 9 flags 11 pri 0:120 r0 elapsed 76938ms node 676995229 size 132:0 offset da8
    pending async transaction 837268622: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 76638ms node 676995229 size 320:0 offset e30
    pending async transaction 837269172: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 75606ms node 676995229 size 320:0 offset 10c8
    pending async transaction 837269239: 0000000000000000 from 7355:7384 to 2867:0 code 1 flags 11 pri 0:120 r0 elapsed 75257ms node 676995229 size 416:0 offset 1308
    pending async transaction 837269242: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 75255ms node 676995229 size 320:0 offset 1678
    pending async transaction 837269352: 0000000000000000 from 7355:7384 to 2867:0 code a flags 11 pri 0:120 r0 elapsed 75009ms node 676995229 size 200:0 offset 1af8
    pending async transaction 837269381: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 74890ms node 676995229 size 156:0 offset 1d60
    pending async transaction 837269446: 0000000000000000 from 7355:7384 to 2867:0 code 3 flags 11 pri 0:120 r0 elapsed 74497ms node 676995229 size 1308:0 offset 20d8
    pending async transaction 837269447: 0000000000000000 from 7355:7384 to 2867:0 code 1 flags 11 pri 0:120 r0 elapsed 74492ms node 676995229 size 416:0 offset 25f8
    pending async transaction 837269495: 0000000000000000 from 7355:7384 to 2867:0 code a flags 11 pri 0:120 r0 elapsed 74297ms node 676995229 size 200:0 offset 2ad8
    pending async transaction 837269610: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 74025ms node 676995229 size 320:0 offset 2d88
    pending async transaction 837269643: 0000000000000000 from 7355:7384 to 2867:0 code 9 flags 11 pri 0:120 r0 elapsed 73929ms node 676995229 size 132:0 offset 2ec8
    pending async transaction 837270539: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 71883ms node 676995229 size 156:0 offset 2f50
    pending async transaction 837270710: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 71104ms node 676995229 size 320:0 offset 2ff0
    pending async transaction 837270742: 0000000000000000 from 7355:7384 to 2867:0 code 9 flags 11 pri 0:120 r0 elapsed 70925ms node 676995229 size 132:0 offset 3130
    pending async transaction 837270812: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 70690ms node 676995229 size 320:0 offset 3390
    pending async transaction 837270867: 0000000000000000 from 7355:7384 to 2867:0 code 3 flags 11 pri 0:120 r0 elapsed 70433ms node 676995229 size 1144:0 offset 34d0
    pending async transaction 837270870: 0000000000000000 from 7355:7384 to 2867:0 code 1 flags 11 pri 0:120 r0 elapsed 70425ms node 676995229 size 416:0 offset 3948
    pending async transaction 837270915: 0000000000000000 from 7355:7384 to 2867:0 code a flags 11 pri 0:120 r0 elapsed 70160ms node 676995229 size 200:0 offset 3d70
    pending async transaction 837271141: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 68881ms node 676995229 size 156:0 offset 40d8
    pending async transaction 837271498: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 68433ms node 676995229 size 320:0 offset 41f8
    pending async transaction 837271677: 0000000000000000 from 7355:7384 to 2867:0 code 9 flags 11 pri 0:120 r0 elapsed 67924ms node 676995229 size 132:0 offset 43b8
    pending async transaction 837272089: 0000000000000000 from 7355:7384 to 2867:0 code 3 flags 11 pri 0:120 r0 elapsed 66778ms node 676995229 size 1308:0 offset 4770
    pending async transaction 837272090: 0000000000000000 from 7355:7384 to 2867:0 code 1 flags 11 pri 0:120 r0 elapsed 66774ms node 676995229 size 416:0 offset 4c90
    pending async transaction 837272203: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 66484ms node 676995229 size 320:0 offset 4e30
    pending async transaction 837272332: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 65883ms node 676995229 size 156:0 offset 5068
    pending async transaction 837272343: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 65832ms node 676995229 size 320:0 offset 5108
    pending async transaction 837272514: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 65099ms node 676995229 size 320:0 offset 5418
    pending async transaction 837272543: 0000000000000000 from 7355:7384 to 2867:0 code 9 flags 11 pri 0:120 r0 elapsed 64924ms node 676995229 size 132:0 offset 5918
    pending async transaction 837272622: 0000000000000000 from 7355:7384 to 2867:0 code 3 flags 11 pri 0:120 r0 elapsed 64505ms node 676995229 size 324:0 offset 5c98
    pending async transaction 837272625: 0000000000000000 from 7355:7384 to 2867:0 code 1 flags 11 pri 0:120 r0 elapsed 64501ms node 676995229 size 416:0 offset 5de0
    pending async transaction 837272638: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 64446ms node 676995229 size 320:0 offset 6530
    pending async transaction 837272703: 0000000000000000 from 7355:7384 to 2867:0 code 9 flags 11 pri 0:120 r0 elapsed 64053ms node 676995229 size 132:0 offset 6670
    pending async transaction 837272822: 0000000000000000 from 7355:7384 to 2867:0 code a flags 11 pri 0:120 r0 elapsed 63741ms node 676995229 size 200:0 offset 6af0
    pending async transaction 837273132: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 62604ms node 676995229 size 156:0 offset 6ef0
    pending async transaction 837273379: 0000000000000000 from 7355:7384 to 2867:0 code 9 flags 11 pri 0:120 r0 elapsed 61922ms node 676995229 size 132:0 offset 7170
    pending async transaction 837273387: 0000000000000000 from 7355:7384 to 2867:0 code 3 flags 11 pri 0:120 r0 elapsed 61877ms node 676995229 size 2456:0 offset 7308
    pending async transaction 837273388: 0000000000000000 from 7355:7384 to 2867:0 code 1 flags 11 pri 0:120 r0 elapsed 61877ms node 676995229 size 416:0 offset 7ca0
    pending async transaction 837273400: 0000000000000000 from 7355:7384 to 2867:0 code 9 flags 11 pri 0:120 r0 elapsed 61816ms node 676995229 size 132:0 offset 8060
    pending async transaction 837273428: 0000000000000000 from 7355:7384 to 2867:0 code a flags 11 pri 0:120 r0 elapsed 61654ms node 676995229 size 200:0 offset 87a0
    pending async transaction 837273565: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 61329ms node 676995229 size 320:0 offset 9388
    pending async transaction 837274112: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 60046ms node 676995229 size 320:0 offset 95d8
    pending async transaction 837274818: 0000000000000000 from 7355:7384 to 2867:0 code 9 flags 11 pri 0:120 r0 elapsed 58896ms node 676995229 size 132:0 offset 9718
    pending async transaction 837275806: 0000000000000000 from 7355:7384 to 2867:0 code 9 flags 11 pri 0:120 r0 elapsed 55915ms node 676995229 size 132:0 offset 368
    pending async transaction 837276012: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 54928ms node 676995229 size 320:0 offset 9820
    pending async transaction 837276274: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 53647ms node 676995229 size 320:0 offset 9960
    pending async transaction 837276475: 0000000000000000 from 7355:7384 to 2867:0 code 9 flags 11 pri 0:120 r0 elapsed 52915ms node 676995229 size 132:0 offset 9b30
    pending async transaction 837276892: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 50768ms node 676995229 size 320:0 offset 9bb8
    pending async transaction 837277061: 0000000000000000 from 7355:7384 to 2867:0 code 9 flags 11 pri 0:120 r0 elapsed 49913ms node 676995229 size 132:0 offset 9cf8
    pending async transaction 837277469: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 48845ms node 676995229 size 320:0 offset 9d80
    pending async transaction 837277606: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 48204ms node 676995229 size 320:0 offset 9ec0
    pending async transaction 837277801: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 47246ms node 676995229 size 320:0 offset a000
    pending async transaction 837277927: 0000000000000000 from 7355:7384 to 2867:0 code 9 flags 11 pri 0:120 r0 elapsed 46908ms node 676995229 size 132:0 offset a140
    pending async transaction 837278333: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 45329ms node 676995229 size 320:0 offset a1c8
    pending async transaction 837278617: 0000000000000000 from 7355:7384 to 2867:0 code 9 flags 11 pri 0:120 r0 elapsed 43904ms node 676995229 size 132:0 offset a308
    pending async transaction 837279260: 0000000000000000 from 7355:7384 to 2867:0 code 9 flags 11 pri 0:120 r0 elapsed 40900ms node 676995229 size 132:0 offset a390
    pending async transaction 837279310: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 40526ms node 676995229 size 320:0 offset a418
    pending async transaction 837279411: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 39888ms node 676995229 size 320:0 offset a558
    pending async transaction 837279789: 0000000000000000 from 7355:7384 to 2867:0 code 9 flags 11 pri 0:120 r0 elapsed 37896ms node 676995229 size 132:0 offset a718
    pending async transaction 837280271: 0000000000000000 from 7355:7384 to 2867:0 code 9 flags 11 pri 0:120 r0 elapsed 34890ms node 676995229 size 132:0 offset a7a0
    pending async transaction 837280290: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 34766ms node 676995229 size 320:0 offset a828
    pending async transaction 837280685: 0000000000000000 from 7355:7384 to 2867:0 code 9 flags 11 pri 0:120 r0 elapsed 31886ms node 676995229 size 132:0 offset a968
    pending async transaction 837280686: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 31885ms node 676995229 size 320:0 offset a9f0
    pending async transaction 837281076: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 29645ms node 676995229 size 320:0 offset ab30
    pending async transaction 837281218: 0000000000000000 from 7355:7384 to 2867:0 code 9 flags 11 pri 0:120 r0 elapsed 28883ms node 676995229 size 132:0 offset ac70
    pending async transaction 837281377: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 28045ms node 676995229 size 320:0 offset acf8
    pending async transaction 837281818: 0000000000000000 from 7355:7384 to 2867:0 code 9 flags 11 pri 0:120 r0 elapsed 25879ms node 676995229 size 132:0 offset ae38
    pending async transaction 837281828: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 25804ms node 676995229 size 320:0 offset aec0
    pending async transaction 837281958: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 24844ms node 676995229 size 320:0 offset b000
    pending async transaction 837282165: 0000000000000000 from 7355:7384 to 2867:0 code 3 flags 11 pri 0:120 r0 elapsed 23680ms node 676995229 size 1964:0 offset b448
    pending async transaction 837282166: 0000000000000000 from 7355:7384 to 2867:0 code 1 flags 11 pri 0:120 r0 elapsed 23679ms node 676995229 size 416:0 offset bbf8
    pending async transaction 837282178: 0000000000000000 from 7355:7384 to 2867:0 code 9 flags 11 pri 0:120 r0 elapsed 23608ms node 676995229 size 132:0 offset bd98
    pending async transaction 837282180: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 23606ms node 676995229 size 320:0 offset bed8
    pending async transaction 837282204: 0000000000000000 from 7355:7384 to 2867:0 code a flags 11 pri 0:120 r0 elapsed 23483ms node 676995229 size 200:0 offset c830
    pending async transaction 837282249: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 23247ms node 676995229 size 320:0 offset cc78
    pending async transaction 837282322: 0000000000000000 from 7355:7384 to 2867:0 code 9 flags 11 pri 0:120 r0 elapsed 22878ms node 676995229 size 132:0 offset ceb8
    pending async transaction 837283272: 0000000000000000 from 7355:7384 to 2867:0 code 9 flags 11 pri 0:120 r0 elapsed 19876ms node 676995229 size 132:0 offset cfc0
    pending async transaction 837283533: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 18127ms node 676995229 size 320:0 offset d048
    pending async transaction 837283676: 0000000000000000 from 7355:7384 to 2867:0 code 3 flags 11 pri 0:120 r0 elapsed 17676ms node 676995229 size 2128:0 offset d368
    pending async transaction 837283677: 0000000000000000 from 7355:7384 to 2867:0 code 1 flags 11 pri 0:120 r0 elapsed 17676ms node 676995229 size 416:0 offset dbb8
    pending async transaction 837283687: 0000000000000000 from 7355:7384 to 2867:0 code 9 flags 11 pri 0:120 r0 elapsed 17610ms node 676995229 size 132:0 offset dd58
    pending async transaction 837283689: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 17605ms node 676995229 size 320:0 offset de98
    pending async transaction 837283709: 0000000000000000 from 7355:7384 to 2867:0 code a flags 11 pri 0:120 r0 elapsed 17483ms node 676995229 size 200:0 offset e318
    pending async transaction 837283763: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 17170ms node 676995229 size 320:0 offset e7a8
    pending async transaction 837283820: 0000000000000000 from 7355:7384 to 2867:0 code 9 flags 11 pri 0:120 r0 elapsed 16873ms node 676995229 size 132:0 offset e8e8
    pending async transaction 837284041: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 15884ms node 676995229 size 320:0 offset e970
    pending async transaction 837284083: 0000000000000000 from 7355:7384 to 2867:0 code 3 flags 11 pri 0:120 r0 elapsed 15653ms node 676995229 size 2128:0 offset f0b0
    pending async transaction 837284084: 0000000000000000 from 7355:7384 to 2867:0 code 1 flags 11 pri 0:120 r0 elapsed 15653ms node 676995229 size 416:0 offset f900
    pending async transaction 837284105: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 15525ms node 676995229 size 320:0 offset fd28
    pending async transaction 837284418: 0000000000000000 from 7355:7384 to 2867:0 code 9 flags 11 pri 0:120 r0 elapsed 13871ms node 676995229 size 132:0 offset 10378
    pending async transaction 837285006: 0000000000000000 from 7355:7384 to 2867:0 code 9 flags 11 pri 0:120 r0 elapsed 10870ms node 676995229 size 132:0 offset 105a0
    pending async transaction 837285074: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 10408ms node 676995229 size 320:0 offset 10628
    pending async transaction 837285659: 0000000000000000 from 7355:7384 to 2867:0 code 9 flags 11 pri 0:120 r0 elapsed 7863ms node 676995229 size 132:0 offset 107e8
    pending async transaction 837286253: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 5286ms node 676995229 size 320:0 offset 10960
    pending async transaction 837286365: 0000000000000000 from 7355:7384 to 2867:0 code 9 flags 11 pri 0:120 r0 elapsed 4865ms node 676995229 size 132:0 offset 10aa0
    pending async transaction 837286765: 0000000000000000 from 7355:7384 to 2867:0 code 6 flags 11 pri 0:120 r0 elapsed 2406ms node 676995229 size 320:0 offset 10b28
    pending async transaction 837286911: 0000000000000000 from 7355:7384 to 2867:0 code 9 flags 11 pri 0:120 r0 elapsed 1864ms node 676995229 size 132:0 offset 10c68
  node 52399: ub400007bfca6eb90 cb400007c4ca28e10 pri 0:139 hs 1 hw 1 ls 17 lw 0 is 29 iw 29 tr 1 proc 18107 7982 16412 16157 12384 12254 11690 11258 7739 30810 3317 16066 22022 14237 16834 31727 1716 9779 10280 30857 29399 16454 4464 2885 2796 2576 2923 2055 447
    pending async transaction 837283379: 0000000000000000 from 2055:2424 to 2867:0 code 120 flags 11 pri 0:120 r0 elapsed 19197ms node 52399 size 100:0 offset 3f0
    pending async transaction 837284240: 0000000000000000 from 2055:2424 to 2867:0 code 120 flags 11 pri 0:120 r0 elapsed 14639ms node 52399 size 100:0 offset 100a0
    pending async transaction 837284256: 0000000000000000 from 2055:2424 to 2867:0 code 120 flags 11 pri 0:120 r0 elapsed 14536ms node 52399 size 100:0 offset 10108
    pending async transaction 837284272: 0000000000000000 from 2055:2424 to 2867:0 code 120 flags 11 pri 0:120 r0 elapsed 14431ms node 52399 size 100:0 offset 10170
    pending async transaction 837284290: 0000000000000000 from 2055:2424 to 2867:0 code 120 flags 11 pri 0:120 r0 elapsed 14316ms node 52399 size 100:0 offset 101d8
    pending async transaction 837284360: 0000000000000000 from 2055:2424 to 2867:0 code 120 flags 11 pri 0:120 r0 elapsed 14205ms node 52399 size 100:0 offset 10240
    pending async transaction 837284379: 0000000000000000 from 2055:2424 to 2867:0 code 120 flags 11 pri 0:120 r0 elapsed 14100ms node 52399 size 100:0 offset 102a8
    pending async transaction 837284398: 0000000000000000 from 2055:2424 to 2867:0 code 120 flags 11 pri 0:120 r0 elapsed 13974ms node 52399 size 100:0 offset 10310
    pending async transaction 837284421: 0000000000000000 from 2055:2424 to 2867:0 code 120 flags 11 pri 0:120 r0 elapsed 13869ms node 52399 size 100:0 offset 10400
    pending async transaction 837284439: 0000000000000000 from 2055:2424 to 2867:0 code 120 flags 11 pri 0:120 r0 elapsed 13760ms node 52399 size 100:0 offset 10468
    pending async transaction 837284456: 0000000000000000 from 2055:2424 to 2867:0 code 120 flags 11 pri 0:120 r0 elapsed 13649ms node 52399 size 100:0 offset 104d0
    pending async transaction 837284474: 0000000000000000 from 2055:2424 to 2867:0 code 120 flags 11 pri 0:120 r0 elapsed 13545ms node 52399 size 100:0 offset 10538
  node 676995413: ub400007bfcab2300 cb400007c4ca2a670 pri 0:139 hs 1 hw 1 ls 35 lw 0 is 1 iw 1 tr 1 proc 7355
    pending async transaction 837269240: 0000000000000000 from 7355:7384 to 2867:0 code b flags 11 pri 0:120 r0 elapsed 75258ms node 676995413 size 244:0 offset 14a8
    pending async transaction 837269245: 0000000000000000 from 7355:7384 to 2867:0 code 10 flags 11 pri 0:120 r0 elapsed 75255ms node 676995413 size 184:0 offset 17b8
    pending async transaction 837269347: 0000000000000000 from 7355:7384 to 2867:0 code b flags 11 pri 0:120 r0 elapsed 75018ms node 676995413 size 244:0 offset 1870
    pending async transaction 837269349: 0000000000000000 from 7355:7384 to 2867:0 code f flags 11 pri 0:120 r0 elapsed 75016ms node 676995413 size 180:0 offset 1a40
    pending async transaction 837269354: 0000000000000000 from 7355:7384 to 2867:0 code 10 flags 11 pri 0:120 r0 elapsed 75005ms node 676995413 size 184:0 offset 1bc0
    pending async transaction 837269361: 0000000000000000 from 7355:7384 to 2867:0 code 12 flags 11 pri 0:120 r0 elapsed 74970ms node 676995413 size 228:0 offset 1c78
    pending async transaction 837269486: 0000000000000000 from 7355:7384 to 2867:0 code b flags 11 pri 0:120 r0 elapsed 74314ms node 676995413 size 244:0 offset 2798
    pending async transaction 837269488: 0000000000000000 from 7355:7384 to 2867:0 code f flags 11 pri 0:120 r0 elapsed 74313ms node 676995413 size 180:0 offset 2968
    pending async transaction 837269491: 0000000000000000 from 7355:7384 to 2867:0 code 10 flags 11 pri 0:120 r0 elapsed 74304ms node 676995413 size 184:0 offset 2a20
    pending async transaction 837269506: 0000000000000000 from 7355:7384 to 2867:0 code 12 flags 11 pri 0:120 r0 elapsed 74243ms node 676995413 size 228:0 offset 2ba0
    pending async transaction 837270912: 0000000000000000 from 7355:7384 to 2867:0 code b flags 11 pri 0:120 r0 elapsed 70169ms node 676995413 size 244:0 offset 3ae8
    pending async transaction 837270914: 0000000000000000 from 7355:7384 to 2867:0 code f flags 11 pri 0:120 r0 elapsed 70168ms node 676995413 size 180:0 offset 3cb8
    pending async transaction 837270916: 0000000000000000 from 7355:7384 to 2867:0 code 10 flags 11 pri 0:120 r0 elapsed 70162ms node 676995413 size 184:0 offset 3e38
    pending async transaction 837270925: 0000000000000000 from 7355:7384 to 2867:0 code 12 flags 11 pri 0:120 r0 elapsed 70094ms node 676995413 size 228:0 offset 3ef0
    pending async transaction 837272511: 0000000000000000 from 7355:7384 to 2867:0 code b flags 11 pri 0:120 r0 elapsed 65102ms node 676995413 size 244:0 offset 5248
    pending async transaction 837272515: 0000000000000000 from 7355:7384 to 2867:0 code 10 flags 11 pri 0:120 r0 elapsed 65101ms node 676995413 size 184:0 offset 5558
    pending async transaction 837272817: 0000000000000000 from 7355:7384 to 2867:0 code b flags 11 pri 0:120 r0 elapsed 63754ms node 676995413 size 244:0 offset 67b0
    pending async transaction 837272819: 0000000000000000 from 7355:7384 to 2867:0 code f flags 11 pri 0:120 r0 elapsed 63751ms node 676995413 size 180:0 offset 6980
    pending async transaction 837272821: 0000000000000000 from 7355:7384 to 2867:0 code 10 flags 11 pri 0:120 r0 elapsed 63744ms node 676995413 size 184:0 offset 6a38
    pending async transaction 837272837: 0000000000000000 from 7355:7384 to 2867:0 code 12 flags 11 pri 0:120 r0 elapsed 63688ms node 676995413 size 228:0 offset 6bb8
    pending async transaction 837273425: 0000000000000000 from 7355:7384 to 2867:0 code b flags 11 pri 0:120 r0 elapsed 61667ms node 676995413 size 244:0 offset 8518
    pending async transaction 837273427: 0000000000000000 from 7355:7384 to 2867:0 code f flags 11 pri 0:120 r0 elapsed 61664ms node 676995413 size 180:0 offset 86e8
    pending async transaction 837273429: 0000000000000000 from 7355:7384 to 2867:0 code 10 flags 11 pri 0:120 r0 elapsed 61657ms node 676995413 size 184:0 offset 8868
    pending async transaction 837273440: 0000000000000000 from 7355:7384 to 2867:0 code 12 flags 11 pri 0:120 r0 elapsed 61604ms node 676995413 size 228:0 offset 8920
    pending async transaction 837282200: 0000000000000000 from 7355:7384 to 2867:0 code b flags 11 pri 0:120 r0 elapsed 23493ms node 676995413 size 244:0 offset c498
    pending async transaction 837282202: 0000000000000000 from 7355:7384 to 2867:0 code f flags 11 pri 0:120 r0 elapsed 23492ms node 676995413 size 180:0 offset c668
    pending async transaction 837282205: 0000000000000000 from 7355:7384 to 2867:0 code 10 flags 11 pri 0:120 r0 elapsed 23483ms node 676995413 size 184:0 offset c8f8
    pending async transaction 837282223: 0000000000000000 from 7355:7384 to 2867:0 code 12 flags 11 pri 0:120 r0 elapsed 23418ms node 676995413 size 228:0 offset c9b0
    pending async transaction 837283705: 0000000000000000 from 7355:7384 to 2867:0 code b flags 11 pri 0:120 r0 elapsed 17492ms node 676995413 size 244:0 offset dfd8
    pending async transaction 837283707: 0000000000000000 from 7355:7384 to 2867:0 code f flags 11 pri 0:120 r0 elapsed 17491ms node 676995413 size 180:0 offset e1a8
    pending async transaction 837283708: 0000000000000000 from 7355:7384 to 2867:0 code 10 flags 11 pri 0:120 r0 elapsed 17486ms node 676995413 size 184:0 offset e260
    pending async transaction 837283716: 0000000000000000 from 7355:7384 to 2867:0 code 12 flags 11 pri 0:120 r0 elapsed 17445ms node 676995413 size 228:0 offset e3e0
    pending async transaction 837284085: 0000000000000000 from 7355:7384 to 2867:0 code b flags 11 pri 0:120 r0 elapsed 15655ms node 676995413 size 244:0 offset faa0
    pending async transaction 837284087: 0000000000000000 from 7355:7384 to 2867:0 code 10 flags 11 pri 0:120 r0 elapsed 15654ms node 676995413 size 184:0 offset fc70
  node 676995387: ub400007bfcad4680 cb400007c4ca47470 pri 0:139 hs 1 hw 1 ls 83 lw 0 is 1 iw 1 tr 1 proc 7355
    pending async transaction 837267678: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 78306ms node 676995387 size 248:0 offset 530
    pending async transaction 837267879: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 77860ms node 676995387 size 212:0 offset 7c0
    pending async transaction 837267919: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 77781ms node 676995387 size 216:0 offset a90
    pending async transaction 837267921: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 77774ms node 676995387 size 256:0 offset b68
    pending async transaction 837269166: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 75642ms node 676995387 size 216:0 offset ff0
    pending async transaction 837269180: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 75547ms node 676995387 size 256:0 offset 1208
    pending async transaction 837269241: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 75258ms node 676995387 size 212:0 offset 15a0
    pending async transaction 837269348: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 75018ms node 676995387 size 212:0 offset 1968
    pending async transaction 837269397: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 74771ms node 676995387 size 252:0 offset 1e00
    pending async transaction 837269431: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 74600ms node 676995387 size 216:0 offset 1f00
    pending async transaction 837269441: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 74531ms node 676995387 size 256:0 offset 1fd8
    pending async transaction 837269487: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 74314ms node 676995387 size 212:0 offset 2890
    pending async transaction 837269529: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 74087ms node 676995387 size 252:0 offset 2c88
    pending async transaction 837270771: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 70732ms node 676995387 size 216:0 offset 31b8
    pending async transaction 837270772: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 70725ms node 676995387 size 256:0 offset 3290
    pending async transaction 837270913: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 70169ms node 676995387 size 212:0 offset 3be0
    pending async transaction 837270965: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 69961ms node 676995387 size 252:0 offset 3fd8
    pending async transaction 837272032: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 67080ms node 676995387 size 216:0 offset 45a0
    pending async transaction 837272042: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 67044ms node 676995387 size 248:0 offset 4678
    pending async transaction 837272234: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 66297ms node 676995387 size 248:0 offset 4f70
    pending async transaction 837272512: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 65102ms node 676995387 size 212:0 offset 5340
    pending async transaction 837272525: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 65032ms node 676995387 size 220:0 offset 5610
    pending async transaction 837272530: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 65008ms node 676995387 size 256:0 offset 56f0
    pending async transaction 837272533: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 64988ms node 676995387 size 296:0 offset 57f0
    pending async transaction 837272601: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 64606ms node 676995387 size 248:0 offset 59a0
    pending async transaction 837272602: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 64603ms node 676995387 size 216:0 offset 5a98
    pending async transaction 837272619: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 64530ms node 676995387 size 292:0 offset 5b70
    pending async transaction 837272626: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 64491ms node 676995387 size 292:0 offset 5f80
    pending async transaction 837272629: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 64479ms node 676995387 size 292:0 offset 60a8
    pending async transaction 837272633: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 64469ms node 676995387 size 292:0 offset 61d0
    pending async transaction 837272634: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 64459ms node 676995387 size 292:0 offset 62f8
    pending async transaction 837272637: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 64450ms node 676995387 size 268:0 offset 6420
    pending async transaction 837272704: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 64055ms node 676995387 size 180:0 offset 66f8
    pending async transaction 837272818: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 63752ms node 676995387 size 212:0 offset 68a8
    pending async transaction 837272838: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 63688ms node 676995387 size 216:0 offset 6ca0
    pending async transaction 837272839: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 63687ms node 676995387 size 248:0 offset 6d78
    pending async transaction 837273377: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 61932ms node 676995387 size 220:0 offset 6f90
    pending async transaction 837273378: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 61927ms node 676995387 size 256:0 offset 7070
    pending async transaction 837273386: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 61887ms node 676995387 size 268:0 offset 71f8
    pending async transaction 837273391: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 61869ms node 676995387 size 268:0 offset 7e40
    pending async transaction 837273392: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 61857ms node 676995387 size 268:0 offset 7f50
    pending async transaction 837273401: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 61818ms node 676995387 size 180:0 offset 80e8
    pending async transaction 837273402: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 61807ms node 676995387 size 296:0 offset 81a0
    pending async transaction 837273407: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 61786ms node 676995387 size 296:0 offset 82c8
    pending async transaction 837273408: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 61777ms node 676995387 size 296:0 offset 83f0
    pending async transaction 837273426: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 61666ms node 676995387 size 212:0 offset 8610
    pending async transaction 837273441: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 61604ms node 676995387 size 296:0 offset 8a08
    pending async transaction 837273442: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 61604ms node 676995387 size 220:0 offset 8b30
    pending async transaction 837273443: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 61604ms node 676995387 size 256:0 offset 8c10
    pending async transaction 837273446: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 61586ms node 676995387 size 312:0 offset 8d10
    pending async transaction 837273449: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 61576ms node 676995387 size 312:0 offset 8e48
    pending async transaction 837273489: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 61487ms node 676995387 size 296:0 offset 8f80
    pending async transaction 837273538: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 61341ms node 676995387 size 252:0 offset 90a8
    pending async transaction 837273599: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 61242ms node 676995387 size 268:0 offset 94c8
    pending async transaction 837282136: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 23820ms node 676995387 size 220:0 offset b140
    pending async transaction 837282139: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 23805ms node 676995387 size 256:0 offset b220
    pending async transaction 837282153: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 23726ms node 676995387 size 296:0 offset b320
    pending async transaction 837282179: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 23611ms node 676995387 size 180:0 offset be20
    pending async transaction 837282192: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 23525ms node 676995387 size 288:0 offset c018
    pending async transaction 837282193: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 23516ms node 676995387 size 288:0 offset c138
    pending async transaction 837282196: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 23506ms node 676995387 size 288:0 offset c258
    pending async transaction 837282199: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 23494ms node 676995387 size 288:0 offset c378
    pending async transaction 837282201: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 23493ms node 676995387 size 212:0 offset c590
    pending async transaction 837282203: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 23487ms node 676995387 size 268:0 offset c720
    pending async transaction 837282224: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 23417ms node 676995387 size 220:0 offset ca98
    pending async transaction 837282225: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 23417ms node 676995387 size 256:0 offset cb78
    pending async transaction 837282266: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 23195ms node 676995387 size 256:0 offset cdb8
    pending async transaction 837283667: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 17727ms node 676995387 size 256:0 offset d188
    pending async transaction 837283671: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 17722ms node 676995387 size 220:0 offset d288
    pending async transaction 837283688: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 17612ms node 676995387 size 180:0 offset dde0
    pending async transaction 837283706: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 17492ms node 676995387 size 212:0 offset e0d0
    pending async transaction 837283717: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 17445ms node 676995387 size 220:0 offset e4c8
    pending async transaction 837283718: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 17444ms node 676995387 size 256:0 offset e5a8
    pending async transaction 837283759: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 17189ms node 676995387 size 256:0 offset e6a8
    pending async transaction 837284052: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 15849ms node 676995387 size 216:0 offset eab0
    pending async transaction 837284056: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 15834ms node 676995387 size 256:0 offset eb88
    pending async transaction 837284063: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 15779ms node 676995387 size 384:0 offset ec88
    pending async transaction 837284066: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 15769ms node 676995387 size 384:0 offset ee08
    pending async transaction 837284076: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 15698ms node 676995387 size 292:0 offset ef88
    pending async transaction 837284086: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 15655ms node 676995387 size 212:0 offset fb98
    pending async transaction 837284109: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 15498ms node 676995387 size 308:0 offset fe68
    pending async transaction 837284201: 0000000000000000 from 7355:7384 to 2867:0 code 4 flags 11 pri 0:120 r0 elapsed 14899ms node 676995387 size 256:0 offset ffa0
  buffer 31964047: 0 size 124:0:0 delivered
  buffer 31960256: a0 size 176:0:0 delivered
  buffer 31963488: 150 size 176:0:0 active
  buffer 31963596: 200 size 104:0:0 active
  buffer 31968823: 268 size 176:0:0 active
  buffer 31969687: 318 size 72:0:0 active
  buffer 31969438: 368 size 132:0:0 active
  buffer 31977011: 3f0 size 100:0:0 active
  buffer 31961296: 458 size 216:0:0 delivered
  buffer 31961310: 530 size 248:0:0 active
  buffer 31961496: 628 size 156:0:0 delivered
  buffer 31981245: 6c8 size 176:0:0 active
  buffer 31961511: 7c0 size 212:0:0 active
  buffer 31961516: 898 size 320:0:0 active
  buffer 31961518: 9d8 size 184:0:0 delivered
  buffer 31961551: a90 size 216:0:0 active
  buffer 31961553: b68 size 256:0:0 active
  buffer 31961591: c68 size 320:0:0 active
  buffer 31962121: da8 size 132:0:0 active
  buffer 31962254: e30 size 320:0:0 active
  buffer 31962798: ff0 size 216:0:0 active
  buffer 31962804: 10c8 size 320:0:0 active
  buffer 31962812: 1208 size 256:0:0 active
  buffer 31962871: 1308 size 416:0:0 active
  buffer 31962872: 14a8 size 244:0:0 active
  buffer 31962873: 15a0 size 212:0:0 active
  buffer 31962874: 1678 size 320:0:0 active
  buffer 31962877: 17b8 size 184:0:0 active
  buffer 31962979: 1870 size 244:0:0 active
  buffer 31962980: 1968 size 212:0:0 active
  buffer 31962981: 1a40 size 180:0:0 active
  buffer 31962984: 1af8 size 200:0:0 active
  buffer 31962986: 1bc0 size 184:0:0 active
  buffer 31962993: 1c78 size 228:0:0 active
  buffer 31963013: 1d60 size 156:0:0 active
  buffer 31963029: 1e00 size 252:0:0 active
  buffer 31963063: 1f00 size 216:0:0 active
  buffer 31963073: 1fd8 size 256:0:0 active
  buffer 31963078: 20d8 size 1308:0:0 active
  buffer 31963079: 25f8 size 416:0:0 active
  buffer 31963118: 2798 size 244:0:0 active
  buffer 31963119: 2890 size 212:0:0 active
  buffer 31963120: 2968 size 180:0:0 active
  buffer 31963123: 2a20 size 184:0:0 active
  buffer 31963127: 2ad8 size 200:0:0 active
  buffer 31963138: 2ba0 size 228:0:0 active
  buffer 31963161: 2c88 size 252:0:0 active
  buffer 31963242: 2d88 size 320:0:0 active
  buffer 31963275: 2ec8 size 132:0:0 active
  buffer 31964171: 2f50 size 156:0:0 active
  buffer 31964342: 2ff0 size 320:0:0 active
  buffer 31964374: 3130 size 132:0:0 active
  buffer 31964403: 31b8 size 216:0:0 active
  buffer 31964404: 3290 size 256:0:0 active
  buffer 31964444: 3390 size 320:0:0 active
  buffer 31964499: 34d0 size 1144:0:0 active
  buffer 31964502: 3948 size 416:0:0 active
  buffer 31964544: 3ae8 size 244:0:0 active
  buffer 31964545: 3be0 size 212:0:0 active
  buffer 31964546: 3cb8 size 180:0:0 active
  buffer 31964547: 3d70 size 200:0:0 active
  buffer 31964548: 3e38 size 184:0:0 active
  buffer 31964557: 3ef0 size 228:0:0 active
  buffer 31964597: 3fd8 size 252:0:0 active
  buffer 31964773: 40d8 size 156:0:0 active
  buffer 31964922: 4178 size 124:0:0 active
  buffer 31965130: 41f8 size 320:0:0 active
  buffer 31965206: 4338 size 124:0:0 active
  buffer 31965309: 43b8 size 132:0:0 active
  buffer 31969173: 4440 size 104:0:0 active
  buffer 31965531: 44b8 size 104:0:0 active
  buffer 31965613: 4520 size 124:0:0 active
  buffer 31965664: 45a0 size 216:0:0 active
  buffer 31965674: 4678 size 248:0:0 active
  buffer 31965721: 4770 size 1308:0:0 active
  buffer 31965722: 4c90 size 416:0:0 active
  buffer 31965835: 4e30 size 320:0:0 active
  buffer 31965866: 4f70 size 248:0:0 active
  buffer 31965964: 5068 size 156:0:0 active
  buffer 31965975: 5108 size 320:0:0 active
  buffer 31966143: 5248 size 244:0:0 active
  buffer 31966144: 5340 size 212:0:0 active
  buffer 31966146: 5418 size 320:0:0 active
  buffer 31966147: 5558 size 184:0:0 active
  buffer 31966157: 5610 size 220:0:0 active
  buffer 31966162: 56f0 size 256:0:0 active
  buffer 31966165: 57f0 size 296:0:0 active
  buffer 31966175: 5918 size 132:0:0 active
  buffer 31966233: 59a0 size 248:0:0 active
  buffer 31966234: 5a98 size 216:0:0 active
  buffer 31966251: 5b70 size 292:0:0 active
  buffer 31966254: 5c98 size 324:0:0 active
  buffer 31966257: 5de0 size 416:0:0 active
  buffer 31966258: 5f80 size 292:0:0 active
  buffer 31966261: 60a8 size 292:0:0 active
  buffer 31966265: 61d0 size 292:0:0 active
  buffer 31966266: 62f8 size 292:0:0 active
  buffer 31966269: 6420 size 268:0:0 active
  buffer 31966270: 6530 size 320:0:0 active
  buffer 31966335: 6670 size 132:0:0 active
  buffer 31966336: 66f8 size 180:0:0 active
  buffer 31966449: 67b0 size 244:0:0 active
  buffer 31966450: 68a8 size 212:0:0 active
  buffer 31966451: 6980 size 180:0:0 active
  buffer 31966453: 6a38 size 184:0:0 active
  buffer 31966454: 6af0 size 200:0:0 active
  buffer 31966469: 6bb8 size 228:0:0 active
  buffer 31966470: 6ca0 size 216:0:0 active
  buffer 31966471: 6d78 size 248:0:0 active
  buffer 31966575: 6e70 size 124:0:0 active
  buffer 31966764: 6ef0 size 156:0:0 active
  buffer 31967009: 6f90 size 220:0:0 active
  buffer 31967010: 7070 size 256:0:0 active
  buffer 31967011: 7170 size 132:0:0 active
  buffer 31967018: 71f8 size 268:0:0 active
  buffer 31967019: 7308 size 2456:0:0 active
  buffer 31967020: 7ca0 size 416:0:0 active
  buffer 31967023: 7e40 size 268:0:0 active
  buffer 31967024: 7f50 size 268:0:0 active
  buffer 31967032: 8060 size 132:0:0 active
  buffer 31967033: 80e8 size 180:0:0 active
  buffer 31967034: 81a0 size 296:0:0 active
  buffer 31967039: 82c8 size 296:0:0 active
  buffer 31967040: 83f0 size 296:0:0 active
  buffer 31967057: 8518 size 244:0:0 active
  buffer 31967058: 8610 size 212:0:0 active
  buffer 31967059: 86e8 size 180:0:0 active
  buffer 31967060: 87a0 size 200:0:0 active
  buffer 31967061: 8868 size 184:0:0 active
  buffer 31967072: 8920 size 228:0:0 active
  buffer 31967073: 8a08 size 296:0:0 active
  buffer 31967074: 8b30 size 220:0:0 active
  buffer 31967075: 8c10 size 256:0:0 active
  buffer 31967078: 8d10 size 312:0:0 active
  buffer 31967081: 8e48 size 312:0:0 active
  buffer 31967121: 8f80 size 296:0:0 active
  buffer 31967170: 90a8 size 252:0:0 active
  buffer 31967197: 9388 size 320:0:0 active
  buffer 31967231: 94c8 size 268:0:0 active
  buffer 31967744: 95d8 size 320:0:0 active
  buffer 31968450: 9718 size 132:0:0 active
  buffer 31968587: 97a0 size 124:0:0 active
  buffer 31969644: 9820 size 320:0:0 active
  buffer 31969906: 9960 size 320:0:0 active
  buffer 31970060: 9aa0 size 132:8:0 delivered
  buffer 31970107: 9b30 size 132:0:0 active
  buffer 31970524: 9bb8 size 320:0:0 active
  buffer 31970693: 9cf8 size 132:0:0 active
  buffer 31971101: 9d80 size 320:0:0 active
  buffer 31971238: 9ec0 size 320:0:0 active
  buffer 31971433: a000 size 320:0:0 active
  buffer 31971559: a140 size 132:0:0 active
  buffer 31971965: a1c8 size 320:0:0 active
  buffer 31972249: a308 size 132:0:0 active
  buffer 31972892: a390 size 132:0:0 active
  buffer 31972942: a418 size 320:0:0 active
  buffer 31973043: a558 size 320:0:0 active
  buffer 31973199: a698 size 124:0:0 active
  buffer 31973421: a718 size 132:0:0 active
  buffer 31973903: a7a0 size 132:0:0 active
  buffer 31973922: a828 size 320:0:0 active
  buffer 31974317: a968 size 132:0:0 active
  buffer 31974318: a9f0 size 320:0:0 active
  buffer 31974708: ab30 size 320:0:0 active
  buffer 31974850: ac70 size 132:0:0 active
  buffer 31975009: acf8 size 320:0:0 active
  buffer 31975450: ae38 size 132:0:0 active
  buffer 31975460: aec0 size 320:0:0 active
  buffer 31975590: b000 size 320:0:0 active
  buffer 31975768: b140 size 220:0:0 active
  buffer 31975771: b220 size 256:0:0 active
  buffer 31975785: b320 size 296:0:0 active
  buffer 31975797: b448 size 1964:0:0 active
  buffer 31975798: bbf8 size 416:0:0 active
  buffer 31975810: bd98 size 132:0:0 active
  buffer 31975811: be20 size 180:0:0 active
  buffer 31975812: bed8 size 320:0:0 active
  buffer 31975824: c018 size 288:0:0 active
  buffer 31975825: c138 size 288:0:0 active
  buffer 31975828: c258 size 288:0:0 active
  buffer 31975831: c378 size 288:0:0 active
  buffer 31975832: c498 size 244:0:0 active
  buffer 31975833: c590 size 212:0:0 active
  buffer 31975834: c668 size 180:0:0 active
  buffer 31975835: c720 size 268:0:0 active
  buffer 31975836: c830 size 200:0:0 active
  buffer 31975837: c8f8 size 184:0:0 active
  buffer 31975855: c9b0 size 228:0:0 active
  buffer 31975856: ca98 size 220:0:0 active
  buffer 31975857: cb78 size 256:0:0 active
  buffer 31975881: cc78 size 320:0:0 active
  buffer 31975898: cdb8 size 256:0:0 active
  buffer 31975954: ceb8 size 132:0:0 active
  buffer 31976301: cf40 size 124:0:0 active
  buffer 31976904: cfc0 size 132:0:0 active
  buffer 31977165: d048 size 320:0:0 active
  buffer 31977299: d188 size 256:0:0 active
  buffer 31977303: d288 size 220:0:0 active
  buffer 31977308: d368 size 2128:0:0 active
  buffer 31977309: dbb8 size 416:0:0 active
  buffer 31977319: dd58 size 132:0:0 active
  buffer 31977320: dde0 size 180:0:0 active
  buffer 31977321: de98 size 320:0:0 active
  buffer 31977337: dfd8 size 244:0:0 active
  buffer 31977338: e0d0 size 212:0:0 active
  buffer 31977339: e1a8 size 180:0:0 active
  buffer 31977340: e260 size 184:0:0 active
  buffer 31977341: e318 size 200:0:0 active
  buffer 31977348: e3e0 size 228:0:0 active
  buffer 31977349: e4c8 size 220:0:0 active
  buffer 31977350: e5a8 size 256:0:0 active
  buffer 31977391: e6a8 size 256:0:0 active
  buffer 31977395: e7a8 size 320:0:0 active
  buffer 31977452: e8e8 size 132:0:0 active
  buffer 31977673: e970 size 320:0:0 active
  buffer 31977684: eab0 size 216:0:0 active
  buffer 31977688: eb88 size 256:0:0 active
  buffer 31977695: ec88 size 384:0:0 active
  buffer 31977698: ee08 size 384:0:0 active
  buffer 31977708: ef88 size 292:0:0 active
  buffer 31977715: f0b0 size 2128:0:0 active
  buffer 31977716: f900 size 416:0:0 active
  buffer 31977717: faa0 size 244:0:0 active
  buffer 31977718: fb98 size 212:0:0 active
  buffer 31977719: fc70 size 184:0:0 active
  buffer 31977737: fd28 size 320:0:0 active
  buffer 31977741: fe68 size 308:0:0 active
  buffer 31977833: ffa0 size 256:0:0 active
  buffer 31977872: 100a0 size 100:0:0 active
  buffer 31977888: 10108 size 100:0:0 active
  buffer 31977904: 10170 size 100:0:0 active
  buffer 31977922: 101d8 size 100:0:0 active
  buffer 31977992: 10240 size 100:0:0 active
  buffer 31978011: 102a8 size 100:0:0 active
  buffer 31978030: 10310 size 100:0:0 active
  buffer 31978050: 10378 size 132:0:0 active
  buffer 31978053: 10400 size 100:0:0 active
  buffer 31978071: 10468 size 100:0:0 active
  buffer 31978088: 104d0 size 100:0:0 active
  buffer 31978106: 10538 size 100:0:0 active
  buffer 31978638: 105a0 size 132:0:0 active
  buffer 31978706: 10628 size 320:0:0 active
  buffer 31978772: 10768 size 124:0:0 active
  buffer 31979291: 107e8 size 132:0:0 active
  buffer 31979503: 10870 size 124:0:0 active
  buffer 31979670: 108f0 size 112:0:0 active
  buffer 31979885: 10960 size 320:0:0 active
  buffer 31979997: 10aa0 size 132:0:0 active
  buffer 31980397: 10b28 size 320:0:0 active
  buffer 31980543: 10c68 size 132:0:0 active
  buffer 31980780: 10cf0 size 240:16:0 delivered
```
