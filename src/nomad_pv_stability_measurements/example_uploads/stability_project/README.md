# PV stability project

A small, made-up stability project that shows how an upload is processed:

- `project_data.xlsx` holds the proposal (as submitted in GATE), two samples with
  their layer stacks, and values for the files.
- `UNITOV/run_1` holds J-V, MPP tracking, parameter and IPCE files of both samples
  in the format of the UNITOV stations; each file becomes an entry linked to its
  sample.
- `HZB/simulation/jv_simulated.csv` is a simulated J-V curve that no reading code
  recognizes; the spreadsheet describes it completely.
- The project entry `project_data.archive.json` is created automatically. It
  imports the spreadsheet, writes one sample entry per sample into the folder
  `samples`, groups the files by sample and plots when each sample was measured.

Edit the project data in NOMAD, or tick "fill archive from data file" in the
project entry to import the spreadsheet again. Values for the files are changed in
the spreadsheet; reprocess the upload so that the files take the changes.
