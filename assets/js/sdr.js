// SDR Lab page: reads sdr-lab/labs.json and lists the files uploaded to sdr-lab/labs/<lab-id>/.
//
// Files are discovered automatically from the GitHub repository (one call to the Git Trees API),
// so uploading a file through github.com is enough — no need to edit labs.json for each file.
//   sdr-lab/labs/lab-01/pre-report/*  -> "Pre-report"
//   sdr-lab/labs/lab-01/report/*      -> "Lab report"
//   sdr-lab/labs/lab-01/files/*       -> "Code & data"
// Files placed directly in sdr-lab/labs/lab-01/ are sorted by name ("pre…" / "…report…" / other).
(function () {
  const LIST = document.getElementById("lab-list");
  const CACHE_KEY = "sdr-tree-v1";
  const CACHE_MS = 5 * 60 * 1000;

  const GROUPS = [
    { key: "pre", label: "Pre-report" },
    { key: "report", label: "Lab report" },
    { key: "files", label: "Code & data" }
  ];

  const STATUS = {
    "done": { cls: "done", label: "Completed" },
    "in-progress": { cls: "progress-s", label: "In progress" },
    "upcoming": { cls: "upcoming", label: "Upcoming" }
  };

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      if (k === "class") node.className = attrs[k];
      else if (k === "text") node.textContent = attrs[k];
      else node.setAttribute(k, attrs[k]);
    });
    (children || []).forEach(function (c) { if (c) node.appendChild(c); });
    return node;
  }

  function formatDate(iso) {
    if (!iso) return "";
    const d = new Date(iso + "T00:00:00");
    if (isNaN(d)) return iso;
    return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  }

  function formatSize(bytes) {
    if (bytes == null) return "";
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + " KB";
    return (bytes / 1024 / 1024).toFixed(1) + " MB";
  }

  function classify(relPath) {
    const parts = relPath.split("/");
    if (parts.length > 1) {
      const dir = parts[0].toLowerCase();
      if (dir.indexOf("pre") === 0) return "pre";
      if (dir.indexOf("report") === 0) return "report";
      return "files";
    }
    const name = parts[0].toLowerCase();
    if (/^pre[-_ ]?(report|lab)|prelab|pre-lab/.test(name)) return "pre";
    if (/report/.test(name)) return "report";
    return "files";
  }

  function isHidden(name) {
    return name.charAt(0) === "." || name.toLowerCase() === "readme.md";
  }

  // ----- Fetch the repository tree (cached in sessionStorage to respect the API rate limit) -----
  function readCache() {
    try {
      const raw = sessionStorage.getItem(CACHE_KEY);
      if (!raw) return null;
      const c = JSON.parse(raw);
      return Date.now() - c.t < CACHE_MS ? c.tree : null;
    } catch (e) { return null; }
  }
  function writeCache(tree) {
    try { sessionStorage.setItem(CACHE_KEY, JSON.stringify({ t: Date.now(), tree: tree })); } catch (e) { /* ignore */ }
  }

  function fetchTree(repo, branch) {
    const cached = readCache();
    if (cached) return Promise.resolve(cached);
    const url = "https://api.github.com/repos/" + repo + "/git/trees/" + encodeURIComponent(branch) + "?recursive=1";
    return fetch(url, { headers: { Accept: "application/vnd.github+json" } })
      .then(function (r) { if (!r.ok) throw new Error("GitHub API " + r.status); return r.json(); })
      .then(function (data) {
        const tree = (data.tree || [])
          .filter(function (n) { return n.type === "blob" && n.path.indexOf("sdr-lab/labs/") === 0; })
          .map(function (n) { return { path: n.path, size: n.size }; });
        writeCache(tree);
        return tree;
      });
  }

  function filesForLab(tree, labId) {
    const prefix = "sdr-lab/labs/" + labId + "/";
    const out = { pre: [], report: [], files: [] };
    tree.forEach(function (n) {
      if (n.path.indexOf(prefix) !== 0) return;
      const rel = n.path.slice(prefix.length);
      const name = rel.split("/").pop();
      if (isHidden(name)) return;
      out[classify(rel)].push({ name: name, rel: rel, size: n.size, path: n.path });
    });
    Object.keys(out).forEach(function (k) { out[k].sort(function (a, b) { return a.name.localeCompare(b.name); }); });
    return out;
  }

  // ----- Rendering -----
  function fileLink(f) {
    // Served by GitHub Pages next to this page: sdr-lab/labs/<id>/...
    const href = f.path.replace(/^sdr-lab\//, "").split("/").map(encodeURIComponent).join("/");
    const ext = (f.name.indexOf(".") > -1 ? f.name.split(".").pop() : "file").slice(0, 5);
    return el("a", { class: "file", href: href, target: "_blank", rel: "noopener", title: f.name }, [
      el("span", { class: "ext", text: ext }),
      el("span", { class: "name", text: f.name }),
      el("span", { class: "size", text: formatSize(f.size) })
    ]);
  }

  function renderFiles(container, files, repoUrl, labId) {
    container.innerHTML = "";
    GROUPS.forEach(function (g) {
      const list = files ? files[g.key] : [];
      const group = el("div", { class: "file-group" }, [el("h4", { text: g.label })]);
      if (list.length) list.forEach(function (f) { group.appendChild(fileLink(f)); });
      else group.appendChild(el("div", { class: "empty", text: "Not uploaded yet" }));
      container.appendChild(group);
    });
    if (!files) {
      const note = el("p", { class: "notice" });
      note.append("Couldn't load the file list right now. ");
      note.appendChild(el("a", { href: repoUrl + "/tree/main/sdr-lab/labs/" + labId, target: "_blank", rel: "noopener", text: "Browse the files on GitHub →" }));
      container.appendChild(note);
    }
  }

  function renderLab(lab, idx) {
    const st = STATUS[lab.status] || STATUS.upcoming;
    const num = String(lab.number != null ? lab.number : idx + 1).padStart(2, "0");

    const sub = el("div", { class: "sub" });
    if (lab.date) sub.appendChild(el("span", { text: "📅 " + formatDate(lab.date) }));
    const countSpan = el("span", { class: "count" });
    sub.appendChild(countSpan);

    const head = el("button", { class: "lab-head", "aria-expanded": "false" }, [
      el("div", { class: "lab-num", text: num }),
      el("div", { class: "lab-title" }, [el("h2", { text: lab.title }), sub]),
      el("div", { class: "lab-right" }, [
        el("span", { class: "status " + st.cls, text: st.label }),
        (function () {
          const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
          s.setAttribute("viewBox", "0 0 24 24"); s.setAttribute("class", "chev");
          s.setAttribute("fill", "none"); s.setAttribute("stroke", "currentColor"); s.setAttribute("stroke-width", "2");
          const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
          p.setAttribute("d", "m6 9 6 6 6-6"); s.appendChild(p); return s;
        })()
      ])
    ]);

    const desc = el("div", { class: "desc" });
    if (lab.summary) desc.appendChild(el("p", { text: lab.summary }));
    if (lab.tasks && lab.tasks.length) {
      const ul = el("ul");
      lab.tasks.forEach(function (t) { ul.appendChild(el("li", { text: t })); });
      desc.appendChild(ul);
    }
    if (lab.page) desc.appendChild(el("a", { class: "btn primary lab-open", href: lab.page, text: "Open the full lab report →" }));
    const filesBox = el("div", { class: "file-groups" }, [el("p", { class: "notice", text: "Loading files…" })]);
    const body = el("div", { class: "lab-body", id: "body-" + lab.id }, [desc, filesBox]);
    head.setAttribute("aria-controls", body.id);

    const card = el("article", { class: "card lab reveal in", id: lab.id }, [head, body]);
    head.addEventListener("click", function () {
      const open = card.classList.toggle("open");
      head.setAttribute("aria-expanded", String(open));
    });
    return { card: card, filesBox: filesBox, countSpan: countSpan };
  }

  function renderCourse(c) {
    document.getElementById("course-title").textContent = c.title || "SDR Lab";
    const meta = document.getElementById("course-meta");
    [["Course code", c.code], ["University", c.university], ["Semester", c.semester], ["Instructor", c.instructor],
     ["Team" + (c.teamName ? " " + c.teamName : ""), (c.team || []).join(", ")]].forEach(function (pair) {
      if (!pair[1]) return;
      const s = el("span");
      s.appendChild(el("b", { text: pair[0] + ": " }));
      s.append(pair[1]);
      meta.appendChild(s);
    });
  }

  function renderStats(labs, totalFiles) {
    const done = labs.filter(function (l) { return l.status === "done"; }).length;
    document.getElementById("stat-labs").textContent = labs.length;
    document.getElementById("stat-done").textContent = done;
    document.getElementById("stat-files").textContent = totalFiles == null ? "–" : totalFiles;
    const pct = labs.length ? Math.round((done / labs.length) * 100) : 0;
    document.getElementById("stat-pct").textContent = pct + "%";
    requestAnimationFrame(function () { document.getElementById("progress-bar").style.width = pct + "%"; });
  }

  fetch("labs.json", { cache: "no-cache" })
    .then(function (r) { return r.json(); })
    .then(function (cfg) {
      const repo = cfg.repo || (location.hostname.replace(".github.io", "") + "/" + location.hostname);
      const repoUrl = "https://github.com/" + repo;
      document.querySelectorAll("[data-repo-link]").forEach(function (a) { a.href = repoUrl + "/tree/main/sdr-lab/labs"; });

      renderCourse(cfg.course || {});
      const labs = (cfg.labs || []).slice().sort(function (a, b) { return (a.number || 0) - (b.number || 0); });
      LIST.innerHTML = "";
      if (!labs.length) LIST.appendChild(el("p", { class: "notice", text: "No lab sessions have been added yet." }));
      const views = labs.map(function (lab, i) { const v = renderLab(lab, i); LIST.appendChild(v.card); return v; });
      renderStats(labs, null);

      // Open the lab named in the URL hash (e.g. #lab-02), otherwise the most recent one.
      const target = labs.findIndex(function (l) { return "#" + l.id === location.hash; });
      const openIdx = target > -1 ? target : views.length - 1;
      if (views[openIdx]) views[openIdx].card.querySelector(".lab-head").click();

      fetchTree(repo, cfg.branch || "main")
        .then(function (tree) {
          let total = 0;
          labs.forEach(function (lab, i) {
            const files = filesForLab(tree, lab.id);
            const n = files.pre.length + files.report.length + files.files.length;
            total += n;
            views[i].countSpan.textContent = n ? "📎 " + n + (n === 1 ? " file" : " files") : "";
            renderFiles(views[i].filesBox, files, repoUrl, lab.id);
          });
          renderStats(labs, total);
        })
        .catch(function () {
          labs.forEach(function (lab, i) { renderFiles(views[i].filesBox, null, repoUrl, lab.id); });
        });
    })
    .catch(function () {
      LIST.innerHTML = "";
      LIST.appendChild(el("p", { class: "notice", text: "Couldn't load labs.json." }));
    });
})();
