# mohammadaminkhoshkam.github.io

Personal website and SDR Lab coursework of Mohammad Amin Khoshkam — live at
**https://mohammadaminkhoshkam.github.io**

```
index.html            ← home page (about, skills, projects, contact)
assets/css/style.css  ← all styles (light + dark theme)
assets/js/main.js     ← theme toggle, menu, animations
assets/js/sdr.js      ← builds the SDR Lab page
sdr-lab/index.html    ← SDR Lab page
sdr-lab/labs.json     ← list of lab sessions (titles, dates, status)
sdr-lab/labs/lab-01/  ← files for each session
    pre-report/       ← pre-report (PDF)
    report/           ← final lab report (PDF)
    files/            ← GNU Radio flowgraphs (.grc), scripts, data, images
```

## Uploading a report (from the GitHub website — no tools needed)

1. Open the repo on github.com and go to `sdr-lab/labs/lab-01/report/`
   (or `pre-report/` / `files/`).
2. Click **Add file → Upload files**, drag your PDF in, and click **Commit changes**.
3. Wait about a minute — the file appears on the SDR Lab page automatically.

> The web uploader accepts files up to 25 MB (GitHub's hard limit is 100 MB per file).
> Compress large captures (`.zip`) before uploading.

## Adding a new lab session

1. Edit `sdr-lab/labs.json` on github.com (pencil icon) and add an entry:

   ```json
   {
     "id": "lab-02",
     "number": 2,
     "title": "AM Modulation and Demodulation",
     "date": "2026-11-12",
     "status": "done",
     "summary": "One or two sentences about what we did.",
     "tasks": ["Generate an AM signal", "Measure the modulation index", "Build an envelope detector"]
   }
   ```

   - `status` is one of `done`, `in-progress`, `upcoming`
   - `date` uses the format `YYYY-MM-DD`
   - remember the comma between entries
2. Upload the files to `sdr-lab/labs/lab-02/pre-report/`, `.../report/` and `.../files/`.
   (When uploading, type the folder path into the file name box, e.g. `lab-02/report/`, and GitHub creates it.)

Course details (code, university, semester, instructor, team members) are at the top of `labs.json`.
