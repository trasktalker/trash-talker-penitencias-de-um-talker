// landing-motion.js - animações da landing (GSAP + ScrollTrigger + Lenis).
// Se os CDNs não carregarem ou o usuário pedir menos movimento, nada é
// escondido e a página fica estática (a classe .js-motion nunca é aplicada).
(function () {
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce || !window.gsap || !window.ScrollTrigger) return;

  var root = document.documentElement;
  root.classList.add("js-motion");
  gsap.registerPlugin(ScrollTrigger);

  // Rolagem suave
  if (window.Lenis) {
    var lenis = new Lenis({ lerp: 0.1 });
    lenis.on("scroll", ScrollTrigger.update);
    gsap.ticker.add(function (t) { lenis.raf(t * 1000); });
    gsap.ticker.lagSmoothing(0);
  }

  // Nav ganha fundo ao rolar
  var nav = document.querySelector(".lm-nav");
  ScrollTrigger.create({
    start: 20,
    onUpdate: function (s) { nav.classList.toggle("is-scrolled", s.scroll() > 20); }
  });

  // Hero: letras sobem por máscara
  document.querySelectorAll("[data-split]").forEach(function (line) {
    var text = line.textContent;
    line.textContent = "";
    text.split("").forEach(function (c) {
      var s = document.createElement("span");
      s.className = "lm-char";
      s.textContent = c === " " ? " " : c;
      line.appendChild(s);
    });
  });
  gsap.timeline({ defaults: { ease: "power4.out" } })
    .to(".lm-char", { y: 0, duration: 1.1, stagger: 0.035 })
    .to(".lm-hero-actions", { opacity: 1, y: 0, duration: 0.8 }, "-=0.5")
    .to(".lm-hero-art", { opacity: 1, duration: 1 }, "-=0.8");

  // Parallax do hero
  document.querySelectorAll("[data-parallax]").forEach(function (el) {
    gsap.to(el, {
      yPercent: parseFloat(el.dataset.parallax) * 100,
      ease: "none",
      scrollTrigger: { trigger: ".lm-hero", start: "top top", end: "bottom top", scrub: true }
    });
  });

  // Manifesto: seção fixa, palavras acendem e as imagens sobem em camadas
  var m = document.querySelector("[data-words]");
  m.innerHTML = m.textContent.trim().split(/\s+/).map(function (w) {
    return '<span class="lm-word">' + w + "</span>";
  }).join(" ");
  // O pin só começa com a seção no topo, mas as palavras já acendem quando a
  // frase entra na tela (senão ela fica apagada durante a rolagem de chegada).
  var pinLength = function () { return Math.round(window.innerHeight * 1.5); };
  ScrollTrigger.create({
    trigger: ".lm-manifesto", start: "top top",
    end: function () { return "+=" + pinLength(); }, pin: true, invalidateOnRefresh: true
  });
  var manifesto = gsap.timeline({
    defaults: { ease: "none" },
    scrollTrigger: {
      trigger: ".lm-manifesto", start: "top 50%", scrub: 0.5, invalidateOnRefresh: true,
      end: function () { return "top+=" + pinLength() + " top"; }
    }
  });
  manifesto.to(".lm-word", { opacity: 1, stagger: 0.1 }, 0);
  var total = manifesto.duration();
  document.querySelectorAll(".lm-float").forEach(function (img) {
    manifesto.to(img, {
      y: parseFloat(img.dataset.speed) * 4,
      rotation: parseFloat(img.dataset.rot) * 3,
      scale: 1.2,
      duration: total
    }, 0);
    // some no fim da animação, antes de a seção soltar
    manifesto.to(img, { opacity: 0, duration: total * 0.2, ease: "power1.in" }, total * 0.8);
  });

  // Personalidades: nome + logo entram de lados opostos
  document.querySelectorAll(".lm-person").forEach(function (p) {
    gsap.from(p.querySelector(".lm-person-head"), {
      xPercent: parseFloat(p.dataset.from) * 25, opacity: 0, ease: "none",
      scrollTrigger: { trigger: p, start: "top 90%", end: "top 45%", scrub: true }
    });
    gsap.from(p.querySelector("p"), {
      y: 30, opacity: 0, duration: 0.8,
      scrollTrigger: { trigger: p, start: "top 60%" }
    });
  });

  // Mascote do MathIAs: balança de leve
  gsap.to(".lm-mascot", { rotation: 6, y: -8, duration: 2.2, ease: "sine.inOut", yoyo: true, repeat: -1 });

  // Como funciona: linha de progresso + passos entrando (sem travar a rolagem)
  gsap.from(".lm-progress-bar", {
    scaleY: 0, ease: "none", transformOrigin: "top",
    scrollTrigger: { trigger: ".lm-steps", start: "top 70%", end: "bottom 60%", scrub: true }
  });
  document.querySelectorAll(".lm-step").forEach(function (step) {
    gsap.from(step.querySelector(".lm-step-num"), {
      x: -80, opacity: 0, ease: "power3.out",
      scrollTrigger: { trigger: step, start: "top 85%", end: "top 55%", scrub: true }
    });
    gsap.from(step.querySelector("div"), {
      x: 80, opacity: 0, ease: "power3.out",
      scrollTrigger: { trigger: step, start: "top 85%", end: "top 55%", scrub: true }
    });
    ScrollTrigger.create({
      trigger: step, start: "top 60%", end: "bottom 40%",
      toggleClass: { targets: step, className: "is-active" }
    });
  });

  // CTA cresce ao entrar
  gsap.from(".lm-cta", {
    scale: 0.85, opacity: 0, ease: "none",
    scrollTrigger: { trigger: ".lm-cta", start: "top 95%", end: "top 55%", scrub: true }
  });

  window.addEventListener("load", function () { ScrollTrigger.refresh(); });
})();
