const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
const heroLedger = document.querySelector(".hero-ledger");
const relay = document.querySelector("[data-relay]");
const replay = document.querySelector("[data-replay]");
const relayStep = document.querySelector(".relay-step");
const relayCaption = document.querySelector(".relay-caption");

const stages = [
  { at: 0, step: "Step 1 of 4", caption: "Finish a useful chunk of work" },
  { at: 1500, step: "Step 2 of 4", caption: "Write one checkpoint to the project file" },
  { at: 3500, step: "Step 3 of 4", caption: "Summarize older notes when the log grows" },
  { at: 5600, step: "Step 4 of 4", caption: "The next agent loads the relevant notes" },
];

let relayTimers = [];

const restartHeroLedger = () => {
  if (!heroLedger || reduceMotion.matches || document.hidden) return;

  const bounds = heroLedger.getBoundingClientRect();
  const isVisible = bounds.bottom > 0 && bounds.top < window.innerHeight;
  if (!isVisible) return;

  heroLedger.classList.remove("is-animating");
  void heroLedger.offsetWidth;
  heroLedger.classList.add("is-animating");
};

const clearRelayTimers = () => {
  relayTimers.forEach(window.clearTimeout);
  relayTimers = [];
};

const showStage = ({ step, caption }) => {
  if (relayStep) relayStep.textContent = step;
  if (relayCaption) relayCaption.textContent = caption;
};

const runRelay = () => {
  if (!relay || reduceMotion.matches) return;

  clearRelayTimers();
  relay.classList.remove("is-running");
  void relay.offsetWidth;
  relay.classList.add("is-running");

  stages.forEach((stage) => {
    relayTimers.push(window.setTimeout(() => showStage(stage), stage.at));
  });
};

document.documentElement.classList.add("motion-ready");

if (heroLedger && !reduceMotion.matches) {
  window.setInterval(restartHeroLedger, 8000);

  const heroLedgerObserver = new IntersectionObserver((entries) => {
    const isVisible = entries.some((entry) => entry.isIntersecting);
    if (isVisible) {
      if (!heroLedger.classList.contains("is-animating")) restartHeroLedger();
      return;
    }

    heroLedger.classList.remove("is-animating");
  }, { threshold: 0.15 });

  heroLedgerObserver.observe(heroLedger);

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      heroLedger.classList.remove("is-animating");
      return;
    }

    restartHeroLedger();
  });
}

if (reduceMotion.matches) {
  showStage({ step: "All 4 stages", caption: "Write, store, summarize, and continue" });
  if (replay) {
    replay.textContent = "Flow shown";
    replay.disabled = true;
  }
} else if (relay) {
  const relayObserver = new IntersectionObserver(
    (entries, observer) => {
      if (!entries.some((entry) => entry.isIntersecting)) return;
      runRelay();
      observer.disconnect();
    },
    { threshold: 0.25, rootMargin: "0px 0px -10% 0px" },
  );

  relayObserver.observe(relay);
  replay?.addEventListener("click", runRelay);
}

const copyText = async (text) => {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Clipboard permissions can be denied even in a secure context.
    }
  }

  const field = document.createElement("textarea");
  field.value = text;
  field.setAttribute("readonly", "");
  field.className = "copy-buffer";
  document.body.append(field);
  field.select();
  const copied = document.execCommand("copy");
  field.remove();
  return copied;
};

const selectText = (target) => {
  const selection = window.getSelection();
  const range = document.createRange();
  range.selectNodeContents(target);
  selection.removeAllRanges();
  selection.addRange(range);
};

document.querySelectorAll("[data-copy]").forEach((button) => {
  button.addEventListener("click", async () => {
    const target = document.getElementById(button.dataset.copy);
    if (!target) return;

    const original = button.textContent;
    try {
      const copied = await copyText(target.textContent.trim());
      if (!copied) throw new Error("Clipboard unavailable");
      button.textContent = "Copied";
      button.classList.add("is-copied");
    } catch {
      selectText(target);
      button.textContent = "Text selected";
    }

    window.setTimeout(() => {
      button.textContent = original;
      button.classList.remove("is-copied");
    }, 1800);
  });
});
