/* ==========================================================================
   Dard.uz — maket interaktivligi (beta)
   MUHIM: bu FAQAT prototip xulqi. Django + HTMX ulangach bu fayl qisqaradi —
   ovoz berish, forma yuborish va lenta yuklash server javobiga ko'chadi.
   Har bir blokda "-> HTMX" izohi almashtiriladigan joyni ko'rsatadi.
   ========================================================================== */
(function () {
  "use strict";

  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const $ = (sel, root = document) => root.querySelector(sel);

  /* ---------------------------------------------------------------------
     1. MAVZU (yorug'/qorong'i)
     FOUC <head> dagi inline skript orqali oldi olingan; bu yerda faqat toggle.
     --------------------------------------------------------------------- */
  $$("[data-theme-toggle]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const isDark = document.documentElement.classList.toggle("dark");
      localStorage.setItem("dard-theme", isDark ? "dark" : "light");
    });
  });

  /* ---------------------------------------------------------------------
     2. MOBIL DRAWER — fokus tuzog'i (focus trap) + Escape bilan yopish
     --------------------------------------------------------------------- */
  const drawer = $("#mobile-drawer");
  let lastFocused = null;

  function openDrawer() {
    if (!drawer) return;
    lastFocused = document.activeElement;
    drawer.hidden = false;
    drawer.classList.remove("hidden");
    document.body.style.overflow = "hidden";
    $$("[data-drawer-open]").forEach((b) => b.setAttribute("aria-expanded", "true"));
    const first = $("a, button", drawer);
    if (first) first.focus();
  }

  function closeDrawer() {
    if (!drawer) return;
    drawer.classList.add("hidden");
    document.body.style.overflow = "";
    $$("[data-drawer-open]").forEach((b) => b.setAttribute("aria-expanded", "false"));
    if (lastFocused) lastFocused.focus();
  }

  $$("[data-drawer-open]").forEach((b) => b.addEventListener("click", openDrawer));
  $$("[data-drawer-close]").forEach((b) => b.addEventListener("click", closeDrawer));

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (drawer && !drawer.classList.contains("hidden")) closeDrawer();
    const openModal = $("[data-modal]:not(.hidden)");
    if (openModal) closeModal(openModal);
    // Login taklifi ochiq bo'lsa — yopamiz va fokusni tugmaga qaytaramiz
    if (activeHint) {
      const anchor = activeHint.anchor;
      closeLoginHint();
      anchor.focus();
    }
  });

  /* ---------------------------------------------------------------------
     3. OVOZ BERISH — optimistik UI
     Foydalanuvchi 100ms ichida javob ko'radi, so'rov fonda ketadi.
     -> HTMX: hx-post="{% url 'vote' pk %}" hx-swap="outerHTML" hx-target="closest .vote-group"
     --------------------------------------------------------------------- */
  function parseCount(text) {
    return parseInt(String(text).replace(/[^\d-]/g, ""), 10) || 0;
  }

  function formatCount(n) {
    // 1284 -> "1 284" (o'zbekcha ming ajratgichi)
    return n.toLocaleString("uz-UZ").replace(/,/g, " ");
  }

  /* Mehmonmi? Django `base.html` da `<body data-guest="true|false">` yozadi.
     ⚠️ Ilgari bu `?guest=1` dan o'qilardi — u FAQAT maketni sinash uchun
        edi va haqiqiy sessiyada hech qachon rost bo'lmasdi, ya'ni kirmagan
        foydalanuvchi ovoz bergandek ko'rinardi (server esa 401 qaytarardi).
     `?guest=1` alohida maket uchun zaxira sifatida qoldirildi. */
  const IS_GUEST =
    document.body.dataset.guest === "true" ||
    new URLSearchParams(location.search).has("guest");

  /* --- Login taklifi (popover) ------------------------------------------
     Bitta vaqtda faqat BITTASI ochiq bo'ladi. Fokusni O'G'IRLAMAYDI —
     foydalanuvchi harakat o'rtasida, uni uloqtirmaymiz; lekin popover
     tugmadan keyin DOM'da turadi, ya'ni Tab bilan CTA ga yetib boriladi. */
  let activeHint = null;

  /**
   * Ikonka yasaydi. `innerHTML` ATAYLAB ishlatilmaydi — bu fayl kelajakda
   * server matnini ham ko'rsatishi mumkin, shuning uchun DOM API'da qolamiz.
   */
  function icon(pathD, cls, filled) {
    const NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("class", cls);
    if (filled) {
      svg.setAttribute("fill", "currentColor");
    } else {
      svg.setAttribute("fill", "none");
      svg.setAttribute("stroke", "currentColor");
      svg.setAttribute("stroke-width", "2");
      svg.setAttribute("stroke-linecap", "round");
    }
    const path = document.createElementNS(NS, "path");
    path.setAttribute("d", pathD);
    svg.appendChild(path);
    return svg;
  }

  const ICON_CLOSE = "M18 6 6 18M6 6l12 12";
  const ICON_TELEGRAM =
    "M21.9 4.4 18.6 20c-.2 1.1-.9 1.4-1.8.9l-5-3.7-2.4 2.3c-.3.3-.5.5-1 .5l.4-5.1L18 6.4c.4-.4-.1-.6-.6-.2L7.1 12.9 2.2 11.4c-1-.3-1.1-1 .2-1.5L20.5 3c.9-.3 1.7.2 1.4 1.4";

  function closeLoginHint() {
    if (!activeHint) return;
    activeHint.anchor.removeAttribute("aria-describedby");
    activeHint.el.remove();
    activeHint = null;
  }

  function showLoginHint(anchor, title, subtext) {
    closeLoginHint();

    const el = document.createElement("div");
    el.className = "login-hint animate-in";
    el.id = "login-hint";
    el.setAttribute("role", "status"); // ekran o'quvchi e'lon qiladi, fokus ko'chmaydi
    el.dataset.fresh = "1"; // shu bosish siklida yopilib ketmasin

    const head = document.createElement("div");
    head.className = "flex items-start gap-2";

    const text = document.createElement("div");
    text.className = "min-w-0 flex-1";
    const h = document.createElement("p");
    h.className = "text-sm font-bold";
    h.textContent = title;
    const s = document.createElement("p");
    s.className = "mt-1 text-[13px] leading-relaxed text-fg-muted";
    s.textContent = subtext;
    text.append(h, s);

    const close = document.createElement("button");
    close.type = "button";
    // Manfiy margin: 44px bosish maydoni saqlanadi, lekin popover kengaymaydi
    close.className = "btn-ghost !px-0 -mr-1.5 -mt-1.5 shrink-0";
    close.setAttribute("aria-label", "Yopish");
    close.appendChild(icon(ICON_CLOSE, "h-4 w-4", false));
    close.addEventListener("click", () => {
      closeLoginHint();
      anchor.focus(); // fokus tugmaga qaytadi, yo'qolmaydi
    });

    head.append(text, close);

    const cta = document.createElement("a");
    /* ⚠️ Maketda `login.html` edi — Django'da bu 404 beradi.
       Manzil `<body data-login-url>` dan olinadi, JS'ga qotirilmaydi:
       URL'lar `urls.py` da o'zgarishi mumkin. */
    cta.href = document.body.dataset.loginUrl || "/kirish/";
    cta.className = "btn-telegram btn-sm mt-3 w-full";
    cta.appendChild(icon(ICON_TELEGRAM, "h-4 w-4", true));
    cta.appendChild(document.createTextNode("Telegram orqali kirish"));

    el.append(head, cta);
    el.style.top = "-9999px"; // o'lchashdan oldin ko'rinmasin
    document.body.appendChild(el);

    // Joylashtirish: tugma ostida, ekranga sig'masa — ustida.
    const a = anchor.getBoundingClientRect();
    const b = el.getBoundingClientRect();
    const M = 8;
    let top = a.bottom + M;
    if (top + b.height > window.innerHeight - M) top = a.top - b.height - M;
    top = Math.max(M, top);
    let left = a.left + a.width / 2 - b.width / 2;
    left = Math.max(M, Math.min(left, window.innerWidth - b.width - M));
    el.style.top = top + "px";
    el.style.left = left + "px";

    anchor.setAttribute("aria-describedby", "login-hint");
    activeHint = { el, anchor };
  }

  // Yopish yo'llari: tashqariga bosish, Escape, skroll, o'lcham o'zgarishi
  document.addEventListener("click", (e) => {
    if (!activeHint) return;
    if (activeHint.el.dataset.fresh) {
      delete activeHint.el.dataset.fresh; // ochgan bosishning o'zi yopmasin
      return;
    }
    if (activeHint.el.contains(e.target) || activeHint.anchor.contains(e.target)) return;
    closeLoginHint();
  });
  window.addEventListener("scroll", closeLoginHint, { passive: true });
  window.addEventListener("resize", closeLoginHint);

  /**
   * Kirmagan foydalanuvchi ovoz berishga urinsa nima bo'ladi?
   *
   * TANLANGAN YO'L: C — ovoz TO'XTATILADI, tugma yonida login taklifi chiqadi.
   *
   * Nega A emas: darhol login sahifasiga uloqtirish odamni lentadan uzadi —
   *   u qaysi postga ovoz bermoqchi bo'lganini yo'qotadi.
   * Nega B emas: ovozni "hisoblangandek" ko'rsatib, keyin kirmasa yo'qotish —
   *   bu yolg'on tasdiq. Dard.uz'da ishonch asosiy valyuta, uni buzmaymiz.
   *
   * @param {HTMLElement} btn  bosilgan ovoz tugmasi
   * @returns {boolean}  false -> ovoz to'xtatiladi
   */
  function handleGuestVote(btn) {
    showLoginHint(
      btn,
      "Ovoz berish uchun kiring",
      "Bir odam — bir ovoz. O'qish uchun kirish shart emas."
    );
    if (navigator.vibrate) navigator.vibrate(12);
    return false;
  }

  /* ⚠️ DELEGATSIYA, har tugmaga alohida listener EMAS.
     Sabab: HTMX ovozdan keyin butun kartani ALMASHTIRADI. Elementga
     bog'langan listener yangi DOM tugunida yo'q bo'lardi — birinchi ovoz
     ishlab, ikkinchisi "o'lik" bo'lib qolardi (optimistik yangilanish
     yo'qoladi, mehmon taklifi chiqmaydi). Buni topish qiyin: HTMX
     so'rovi baribir ketaveradi. */
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-vote]");
    if (btn) {
      /* ⚠️ `preventDefault` SHART: tugma endi `type="submit"` (forma
         JavaScript'siz ham ishlashi uchun). Usiz mehmon bosganda
         popover ham chiqib, forma ham yuborilardi. */
      if (IS_GUEST) {
        e.preventDefault();
        handleGuestVote(btn);
        return;
      }

      const group = btn.closest(".flex, .card") || document;
      const counter = $("[data-vote-count]", btn.parentElement) || $("[data-vote-count]", group);
      if (!counter) return;

      const dir = btn.dataset.vote === "up" ? 1 : -1;
      const wasPressed = btn.getAttribute("aria-pressed") === "true";
      const sibling = $$("[data-vote]", btn.parentElement).find((b) => b !== btn);
      const siblingWasPressed = sibling && sibling.getAttribute("aria-pressed") === "true";

      let count = parseCount(counter.textContent);

      if (wasPressed) {
        count -= dir; // ovozni qaytarib olish
        btn.setAttribute("aria-pressed", "false");
      } else {
        count += dir;
        if (siblingWasPressed) {
          count += dir; // qarama-qarshi ovozdan almashish: ikki barobar
          sibling.setAttribute("aria-pressed", "false");
        }
        btn.setAttribute("aria-pressed", "true");
        btn.classList.remove("animate-pop");
        void btn.offsetWidth; // reflow -> animatsiyani qayta ishga tushirish
        btn.classList.add("animate-pop");
      }

      counter.textContent = formatCount(count);
      counter.classList.toggle("text-upvote", count > 0 && btn.dataset.vote === "up" && !wasPressed);

      // Mobil haptic (qo'llab-quvvatlansa)
      if (navigator.vibrate) navigator.vibrate(8);

      /* Optimistik yangilanish shu yerda TUGAYDI. Keyin HTMX serverdan
         kelgan kartani qo'yadi va u OXIRGI SO'Z bo'ladi: agar sanoq
         boshqacha bo'lsa (masalan boshqa qurilmadan ovoz berilgan),
         serverniki g'olib chiqadi. */
    }
  });

  /* ---------------------------------------------------------------------
     4. TOAST — aria-live orqali e'lon qilinadi, fokusni O'G'IRLAMAYDI
     --------------------------------------------------------------------- */
  const toastRoot = $("#toast-root");

  function toast(message, variant = "default") {
    if (!toastRoot) return;
    const el = document.createElement("div");
    const tone =
      variant === "success"
        ? "border-solved-icon/40 bg-solved-bg text-solved"
        : variant === "error"
          ? "border-danger/40 bg-danger-bg text-danger"
          : "border-line bg-surface text-fg";
    el.className =
      "animate-in pointer-events-auto flex items-center gap-2 rounded-full border px-4 py-2.5 text-sm font-medium shadow-lg " +
      tone;
    el.setAttribute("role", "status");
    el.textContent = message;
    toastRoot.appendChild(el);
    // 3-5s ichida avtomatik yo'qoladi (UX qoidasi: toast-dismiss)
    setTimeout(() => {
      el.style.transition = "opacity 200ms, transform 200ms";
      el.style.opacity = "0";
      el.style.transform = "translateY(6px)";
      setTimeout(() => el.remove(), 220);
    }, 3200);
  }

  $$("[data-toast]").forEach((btn) => {
    btn.addEventListener("click", () => toast(btn.dataset.toast, btn.dataset.toastVariant || "default"));
  });

  /* ---------------------------------------------------------------------
     5. "YANA YUKLASH" — skeleton bilan (>300ms operatsiya)
     -> HTMX: hx-get="?page={{ next }}" hx-trigger="click" hx-swap="beforeend"
     --------------------------------------------------------------------- */
  $$("[data-load-more]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const skeleton = $("[data-skeleton]");
      btn.disabled = true;
      btn.textContent = "Yuklanmoqda…";
      if (skeleton) skeleton.hidden = false;

      setTimeout(() => {
        if (skeleton) skeleton.hidden = true;
        btn.disabled = false;
        btn.textContent = "Yana yuklash";
        toast("Maketda demo ma'lumot cheklangan", "default");
      }, 900);
    });
  });

  /* ---------------------------------------------------------------------
     6. MODAL (yechimni qabul qilish tasdig'i)
     --------------------------------------------------------------------- */
  function openModal(modal) {
    lastFocused = document.activeElement;
    modal.classList.remove("hidden");
    document.body.style.overflow = "hidden";
    const first = $("button, a, input", modal);
    if (first) first.focus();
  }

  function closeModal(modal) {
    modal.classList.add("hidden");
    document.body.style.overflow = "";
    if (lastFocused) lastFocused.focus();
  }

  $$("[data-modal-open]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const modal = $("#" + btn.dataset.modalOpen);
      if (modal) openModal(modal);
    });
  });

  $$("[data-modal-close]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const modal = btn.closest("[data-modal]");
      if (modal) closeModal(modal);
    });
  });

  /* ---------------------------------------------------------------------
     7. FORMA — matn maydoni o'sishi + belgi hisoblagich + blur validatsiyasi
     UX qoidasi (inline-validation): xato TUGATGANDAN keyin ko'rsatiladi,
     har bosilgan tugmada emas.
     --------------------------------------------------------------------- */
  $$("textarea[data-autogrow]").forEach((ta) => {
    const grow = () => {
      ta.style.height = "auto";
      ta.style.height = Math.min(ta.scrollHeight, 520) + "px";
    };
    ta.addEventListener("input", grow);
    grow();
  });

  $$("[data-counter-for]").forEach((out) => {
    const input = document.getElementById(out.dataset.counterFor);
    if (!input) return;
    const max = parseInt(input.getAttribute("maxlength"), 10) || 0;
    const update = () => {
      const len = input.value.length;
      out.textContent = len + " / " + max;
      out.classList.toggle("text-danger", max > 0 && len > max * 0.95);
    };
    input.addEventListener("input", update);
    update();
  });

  function setFieldError(input, message) {
    const wrap = input.closest("[data-field]");
    if (!wrap) return;
    const err = $("[data-field-error]", wrap);
    if (message) {
      input.classList.add("input-invalid");
      input.setAttribute("aria-invalid", "true");
      if (err) {
        err.textContent = message;
        err.hidden = false;
      }
    } else {
      input.classList.remove("input-invalid");
      input.removeAttribute("aria-invalid");
      if (err) err.hidden = true;
    }
  }

  function validateField(input) {
    const min = parseInt(input.dataset.minlen || "0", 10);
    const value = input.value.trim();
    if (input.required && !value) {
      setFieldError(input, "Bu maydon to'ldirilishi shart.");
      return false;
    }
    if (min && value.length < min) {
      setFieldError(input, `Kamida ${min} ta belgi kerak — hozir ${value.length} ta.`);
      return false;
    }
    setFieldError(input, null);
    return true;
  }

  $$("[data-field] .input").forEach((input) => {
    // blur'da tekshiramiz, har bosishda emas
    input.addEventListener("blur", () => validateField(input));
    // xato ko'rsatilgan bo'lsa — yozayotganda darhol tuzatamiz
    input.addEventListener("input", () => {
      if (input.getAttribute("aria-invalid") === "true") validateField(input);
    });
  });

  /* ⚠️ ILGARI BU YERDA SOXTA YUBORISH BOR EDI (D1-T9 da tuzatildi).
     Maket versiyasi `e.preventDefault()` chaqirib, `setTimeout` bilan
     "Dardingiz e'lon qilindi" toast'ini ko'rsatardi va formani HECH
     QACHON yubormasdi. Backend yo'q paytda bu to'g'ri edi; haqiqiy
     formaga ulanganda esa eng yomon xato turi bo'lardi — foydalanuvchi
     MUVAFFAQIYAT xabarini ko'radi, post esa hech qayerga yozilmaydi.

     Endi: xato bo'lsa to'xtatamiz, yaroqli bo'lsa brauzer formani
     O'ZI yuboradi (server tomonda baribir qayta tekshiriladi). */
  $$("form[data-validate]").forEach((form) => {
    form.addEventListener("submit", (e) => {
      const fields = $$("[data-field] .input", form);
      const invalid = fields.filter((f) => !validateField(f));

      if (invalid.length) {
        e.preventDefault();
        // UX qoidasi (focus-management): birinchi xato maydonga fokus
        invalid[0].focus();
        invalid[0].scrollIntoView({ block: "center", behavior: "smooth" });
        toast("Formada " + invalid.length + " ta xato bor", "error");
        return;
      }

      clearDraft(form);

      const submit = $("[type=submit]", form);
      if (submit) {
        submit.dataset.label = submit.textContent;
        submit.textContent = "Yuborilmoqda…";
        /* ⚠️ `disabled` KEYINGI TIKDA: tugmani darhol o'chirish uning
           `name`/`value` ini yuborishdan chiqarib tashlaydi (ovoz
           formasidagi `qiymat` shunday yo'qolardi). Yuborish
           navbatga qo'yilgandan keyin o'chirish xavfsiz. */
        setTimeout(() => {
          submit.disabled = true;
        }, 0);
      }
    });
  });

  /* ---------------------------------------------------------------------
     7a. QORALAMA AVTOSAQLASH (D1-T9)
     "Uzun forma tasodifan yopilsa matn yo'qoladi — bu foydalanuvchini
     qaytmaydigan qiladi."

     ⚠️ `localStorage`, serverga saqlash EMAS. Sabab: qoralama yozilayotgan
        paytda foydalanuvchi hali hech narsa E'LON QILMAGAN. Har bosilgan
        harfni serverga yuborish — yozilmagan, ehtimol hech qachon
        yozilmaydigan matnni boshqa joyga ko'chirish degani. Og'ir
        mavzuli platformada bu qabul qilinmaydi.

     ⚠️ Kalitga forma manzili kiritiladi: yaratish va tahrirlash formalari
        bir-birining matnini tortib olmasin.
     --------------------------------------------------------------------- */
  const DRAFT_PREFIX = "dard-draft:";

  function draftKey(form) {
    return DRAFT_PREFIX + (form.getAttribute("action") || location.pathname);
  }

  function clearDraft(form) {
    try {
      localStorage.removeItem(draftKey(form));
    } catch (_) {
      /* xususiy rejim yoki kvota — qoralama shunchaki ishlamaydi */
    }
  }

  /* ---------------------------------------------------------------------
     7b. JONLI KO'RINISH — sarlavha yozilgan sari yon paneldagi karta yangilanadi.
     Foydalanuvchi natijani yuborishdan OLDIN ko'radi (progressive feedback).
     --------------------------------------------------------------------- */
  const mirrorSource = $("[data-mirror-source]");
  const mirrorTarget = $("[data-mirror-target]");
  if (mirrorSource && mirrorTarget) {
    const placeholder = mirrorTarget.dataset.mirrorEmpty || "";
    mirrorSource.addEventListener("input", () => {
      const value = mirrorSource.value.trim();
      mirrorTarget.textContent = value || placeholder;
      mirrorTarget.classList.toggle("text-fg-muted", !value);
    });
  }

  /* ⚠️ QORALAMA TIKLASH ENG OXIRIDA EMAS, LEKIN "JONLI KO'RINISH" DAN
     KEYIN turishi shart. Ilgari u yuqorida edi va tiklangan sarlavha
     yon paneldagi kartaga TUSHMASDI: `input` hodisasi yuborilganda
     mirror ishlovchisi hali bog'lanmagan bo'lardi. Natija — maydonda
     matn bor, ko'rinishda esa "Sarlavhangiz shu yerda ko'rinadi".
     Xato emas, lekin foydalanuvchi buni nosozlik deb o'qiydi. */
  $$("form[data-draft]").forEach((form) => {
    const fields = $$("textarea, input[type=text]", form).filter((f) => f.name);
    if (!fields.length) return;
    const key = draftKey(form);

    // 1) Tiklash — FAQAT maydon bo'sh bo'lsa. Server qaytargan qiymat
    //    (masalan validatsiya xatosidan keyin) qoralamadan USTUN.
    try {
      const saqlangan = JSON.parse(localStorage.getItem(key) || "{}");
      let tiklandi = false;
      fields.forEach((f) => {
        if (!f.value && saqlangan[f.name]) {
          f.value = saqlangan[f.name];
          f.dispatchEvent(new Event("input", { bubbles: true }));
          tiklandi = true;
        }
      });
      if (tiklandi) toast("Saqlangan qoralama tiklandi");
    } catch (_) {
      /* buzilgan qoralama — e'tiborsiz qoldiramiz */
    }

    // 2) Saqlash — yozishdan keyin 600ms jimlikda (har harfda emas)
    let taymer = null;
    const saqla = () => {
      clearTimeout(taymer);
      taymer = setTimeout(() => {
        const holat = {};
        fields.forEach((f) => {
          if (f.value) holat[f.name] = f.value;
        });
        try {
          if (Object.keys(holat).length) {
            localStorage.setItem(key, JSON.stringify(holat));
          } else {
            localStorage.removeItem(key);
          }
        } catch (_) {
          /* kvota to'lgan — qoralama shunchaki saqlanmaydi */
        }
      }, 600);
    };
    fields.forEach((f) => f.addEventListener("input", saqla));
  });


  /* ---------------------------------------------------------------------
     8. CHIP FILTRLARI (avlod / saralash)
     -> Django: bular <a href="?generation=genz"> bo'ladi (deep linking).
        Maketda vizual holatni ko'rsatish uchun tugma.
     --------------------------------------------------------------------- */
  $$('[role="group"] .chip').forEach((chip) => {
    chip.addEventListener("click", () => {
      const group = chip.closest('[role="group"]');
      $$(".chip", group).forEach((c) => {
        c.classList.remove("chip-active");
        c.setAttribute("aria-pressed", "false");
      });
      chip.classList.add("chip-active");
      chip.setAttribute("aria-pressed", "true");
    });
  });

  /* ---------------------------------------------------------------------
     9. TABLAR (profil sahifasi) — WCAG: o'q tugmalari bilan boshqariladi
     --------------------------------------------------------------------- */
  const tabLists = $$('[role="tablist"]');
  tabLists.forEach((list) => {
    const tabs = $$('[role="tab"]', list);
    const activeClasses = [
      "text-fg",
      "font-semibold",
      "relative",
      "after:absolute",
      "after:inset-x-2",
      "after:-bottom-px",
      "after:h-0.5",
      "after:bg-primary",
    ];

    function selectTab(tab) {
      tabs.forEach((t) => {
        const panel = document.getElementById(t.dataset.tab);
        const isTarget = t === tab;
        t.setAttribute("aria-selected", String(isTarget));
        t.tabIndex = isTarget ? 0 : -1;
        t.classList.toggle("font-medium", !isTarget);
        t.classList.toggle("text-fg-muted", !isTarget);
        activeClasses.forEach((c) => t.classList.toggle(c, isTarget));
        if (panel) panel.hidden = !isTarget;
      });
    }

    tabs.forEach((tab) => {
      tab.addEventListener("click", () => selectTab(tab));
      tab.addEventListener("keydown", (e) => {
        const i = tabs.indexOf(tab);
        let next = null;
        if (e.key === "ArrowRight") next = tabs[(i + 1) % tabs.length];
        if (e.key === "ArrowLeft") next = tabs[(i - 1 + tabs.length) % tabs.length];
        if (e.key === "Home") next = tabs[0];
        if (e.key === "End") next = tabs[tabs.length - 1];
        if (!next) return;
        e.preventDefault();
        selectTab(next);
        next.focus();
      });
    });
  });

  /* ---------------------------------------------------------------------
     10. YECHIMNI QABUL QILISH — OLIB TASHLANDI (D1-T10)

     ⚠️ Bu yerda maketning SOXTA ishlovchisi turgan edi: u kartani
        vizual "qabul qilingan" qilib bo'yab, "Yechim qabul qilindi —
        muallifga kontakt ochildi" toast'ini ko'rsatardi va SERVERGA
        HECH NIMA YUBORMASDI.

        Backend yo'q paytda bu to'g'ri edi. Haqiqiy oqim ulangandan
        keyin esa u eng yomon turdagi xatoga aylanardi: foydalanuvchi
        muvaffaqiyat xabarini ko'radi, karma berilmaydi, muammo
        "yechilgan" bo'lmaydi — va sahifani yangilaganda hammasi
        yo'qoladi.

        Endi qabul qilish `<form method="post">` orqali ketadi
        (components/_solution.html) va sahifa qayta yuklanadi — sabab
        `apps/solutions/views.py::solution_accept` docstring'ida.
     --------------------------------------------------------------------- */
})();
