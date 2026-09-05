# Shriftlar — server tomonida ishlatiladi

Bu yerdagi fayllar **Open Graph rasmini yasash** uchun (`apps/common/og.py`).
Ular `static/` da EMAS: `collectstatic` ularni yig'ib, nginx bekorga
ommaviy tarqatardi. Saytning o'zi Inter'ni Google Fonts'dan oladi va u
yerda ancha kichik `woff2` beriladi.

| Fayl | Nima |
|---|---|
| `Inter-Regular.ttf` | shior va kategoriya chipi |
| `Inter-Bold.ttf` | brend va sarlavha |
| `Inter-OFL.txt` | SIL Open Font License 1.1 — **tarqatish sharti** |

## ⚠️ Nega ikkita statik fayl, o'zgaruvchan (variable) emas

O'zgaruvchan Inter bitta fayldan to'qqizta og'irlik beradi va bu jozibali
ko'rinadi. Lekin u 876 KB, kerakli belgilarga qisqartirilgandan keyin ham
**513 KB** — chunki `gvar` jadvali (har glif uchun har o'q bo'yicha
o'zgarish ma'lumoti) qisqarmaydi.

`check-added-large-files` hooki (500 KB) uni to'g'ri rad etdi. Bizga esa
faqat ikki og'irlik kerak:

```
o'zgaruvchan, qisqartirilgan    513 KB
ikkita statik, qisqartirilgan   252 KB   <- shu
```

## Qanday yasalgan (takrorlanadigan)

Manba: [google/fonts](https://github.com/google/fonts/tree/main/ofl/inter)
dagi `Inter[opsz,wght].ttf`.

```bash
pip install fonttools brotli        # FAQAT shu ish uchun, requirements'da YO'Q

UNI="U+0000-00FF,U+0100-017F,U+018F,U+0192,U+01A0-01A1,U+01AF-01B0,\
U+02B0-02FF,U+0300-036F,U+2000-206F,U+20A0-20BF,U+2116,U+2122,\
U+2190-2199,U+2212,U+FFFD,U+0400-04FF,U+0500-052F"

for w in 400:Regular 700:Bold; do
  python -m fontTools.varLib.instancer "Inter[opsz,wght].ttf" \
      "wght=${w%%:*}" "opsz=28" -o "/tmp/inter-${w##*:}.ttf"
  python -m fontTools.subset "/tmp/inter-${w##*:}.ttf" \
      --unicodes="$UNI" --output-file="Inter-${w##*:}.ttf"
done
```

Unicode oralig'i: lotin (o'zbek `ʻ` bilan — U+02B0-02FF), kirill
(o'zbekcha `ў қ ғ ҳ` bilan), tinish belgilari va valyuta.

## ⚠️ Almashtirilsa

Shriftda yo'q belgi **bo'sh quti** bo'lib chiziladi — xato chiqmaydi va
buni faqat Telegram'ga havola tashlagan odam ko'radi. Qamrov testi buni
ushlaydi:

```
pytest apps/common/tests/test_og.py -k QAMRAB
```
