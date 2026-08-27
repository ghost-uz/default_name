# Branch himoyasi (D0-T9 qabul mezoni)

> ⚠️ Bu **kodda emas, GitHub sozlamalarida** qilinadi. Shuning uchun alohida
> yozib qo'yilgan — aks holda repo yaratilganda unutiladi va CI bor bo'lsa
> ham hech narsani to'xtatmaydi.

## Nega kerak

CI yashil bo'lmasa ham merge qilish mumkin bo'lsa, CI shunchaki
**ma'lumot beruvchi** bo'lib qoladi. Yolg'iz ishlaganda esa "hozir tez
merge qilaman, keyin tuzataman" degan vasvasa har doim yutadi.

## Sozlash (bir marta)

`Settings → Branches → Add branch ruleset`

| Sozlama | Qiymat |
|---|---|
| Target branches | `main` |
| Require a pull request before merging | ✅ |
| — Required approvals | `0` (yolg'iz ishlanayotgani uchun) |
| Require status checks to pass | ✅ |
| — Required check | **`CI holati`** |
| Require branches to be up to date | ✅ |
| Require conversation resolution | ✅ |
| Block force pushes | ✅ |

### ⚠️ Faqat bitta tekshiruvni tanlang: `CI holati`

`ci.yml` da to'rtta job bor (`sifat`, `test`, `docker`, `ci`), lekin
himoyaga **faqat `CI holati`** (`ci` job'i) bog'lanadi.

Sabab: har bir job'ni alohida tanlasangiz, kelajakda yangi job qo'shilganda
uni himoya ro'yxatiga qo'lda qo'shish kerak bo'ladi — va bu unutiladi.
O'shanda yangi tekshiruv yiqilsa ham merge o'tib ketaveradi.

`ci` job'i qolgan uchtasiga `needs` orqali bog'langan va bittasi yiqilsa
o'zi ham yiqiladi. Yangi job qo'shilsa, faqat uning `needs` ro'yxatiga
qo'shiladi — GitHub sozlamasiga tegilmaydi.

## Sirlar (Secrets)

CI hozircha hech qanday sirga muhtoj emas: testlar `config.settings.test`
bilan ishlaydi va tashqi tarmoq `conftest.py` da taqiqlangan.

Sirlar **D0-T10** (deploy) da kerak bo'ladi:

| Nom | Nima uchun |
|---|---|
| `SSH_PRIVATE_KEY` | serverga ulanish |
| `SSH_HOST`, `SSH_USER` | server manzili |
| `DJANGO_SECRET_KEY` | prod sozlamasi |

⚠️ Ularni hech qachon `.env` yoki workflow faylida yozmang —
`Settings → Secrets and variables → Actions` orqali qo'shiladi.
