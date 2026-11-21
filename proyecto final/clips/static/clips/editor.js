/* Editor de recorte de SparkCut: sin frameworks, solo fetch y sondeo. */
(function () {
  "use strict";

  var tokenInput = document.querySelector("[name=csrfmiddlewaretoken]");
  var csrfToken = tokenInput ? tokenInput.value : "";

  function setNote(card, text, isError) {
    var note = card.querySelector("[data-status]");
    if (!note) return;
    note.textContent = text;
    note.style.color = isError ? "var(--accent-2)" : "var(--muted)";
  }

  async function postJSON(url, body) {
    var response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
        "Accept": "application/json",
      },
      body: JSON.stringify(body || {}),
    });
    var data = {};
    try {
      data = await response.json();
    } catch (error) {
      data = { error: "Respuesta inválida del servidor." };
    }
    return { ok: response.ok, status: response.status, data: data };
  }

  function pollUntilReady(card) {
    var statusUrl = card.getAttribute("data-status-url");
    var attempts = 0;

    async function check() {
      attempts += 1;
      try {
        var response = await fetch(statusUrl, {
          headers: { "Accept": "application/json" },
        });
        if (response.status === 403) {
          setNote(card, "Tu sesión caducó. Recarga la página.", true);
          return;
        }
        var data = await response.json();
        if (data.status === "ready") {
          window.location.reload();
          return;
        }
        if (data.status === "failed") {
          setNote(card, "No se pudo recortar el clip. Inténtalo de nuevo.", true);
          return;
        }
        setNote(card, "Recortando… (" + attempts + ")");
      } catch (error) {
        setNote(card, "Comprobando el estado…");
      }
      setTimeout(check, 1500);
    }

    check();
  }

  document.querySelectorAll(".clip-card").forEach(function (card) {
    var trimButton = card.querySelector("[data-action=trim]");
    var restoreButton = card.querySelector("[data-action=restore]");
    var startInput = card.querySelector("[data-start]");
    var endInput = card.querySelector("[data-end]");

    if (trimButton) {
      trimButton.addEventListener("click", async function () {
        var start = parseFloat(startInput.value);
        var end = parseFloat(endInput.value);

        if (isNaN(start) || isNaN(end)) {
          setNote(card, "Escribe el inicio y el final en segundos.", true);
          return;
        }
        if (end <= start) {
          setNote(card, "El final debe ser mayor que el inicio.", true);
          return;
        }
        if (end - start < 3 || end - start > 90) {
          setNote(card, "La duración debe estar entre 3 y 90 segundos.", true);
          return;
        }

        trimButton.disabled = true;
        setNote(card, "Guardando…");

        var result = await postJSON(card.getAttribute("data-trim-url"), {
          start: start,
          end: end,
        });

        if (result.status === 409) {
          setNote(card, "Ya hay un re-recorte en curso para este clip.", true);
          trimButton.disabled = false;
          pollUntilReady(card);
          return;
        }
        if (!result.ok) {
          setNote(card, result.data.error || "No se pudo guardar el recorte.", true);
          trimButton.disabled = false;
          return;
        }

        setNote(card, "Recortando…");
        pollUntilReady(card);
      });
    }

    if (restoreButton) {
      restoreButton.addEventListener("click", async function () {
        restoreButton.disabled = true;
        setNote(card, "Restaurando el recorte original…");

        var result = await postJSON(card.getAttribute("data-restore-url"));

        if (result.status === 409) {
          setNote(card, "Ya hay un re-recorte en curso para este clip.", true);
          restoreButton.disabled = false;
          return;
        }
        if (!result.ok) {
          setNote(card, result.data.error || "No se pudo restaurar el clip.", true);
          restoreButton.disabled = false;
          return;
        }
        if (result.data.status === "ready") {
          setNote(card, result.data.message || "El clip no tenía cambios.");
          restoreButton.disabled = false;
          return;
        }
        setNote(card, "Recortando…");
        pollUntilReady(card);
      });
    }
  });
})();
