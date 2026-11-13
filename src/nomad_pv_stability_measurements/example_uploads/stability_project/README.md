# PV stability project

A small, made-up stability project that shows how an upload is processed:

- `project_data.xlsx` holds the proposal (as submitted in GATE), two samples with
  their layer stacks, and values for the files.
- `UNITOV/run_1` holds J-V, MPP tracking, parameter and IPCE files of both samples
  in the format of the UNITOV stations; each file becomes an entry linked to its
  sample.
- `HZB/simulation/jv_simulated.csv` is a simulated J-V curve that no reading code
  recognizes; the spreadsheet describes it completely, as of sample RPV-S1.
- `simulation/degradation_model.csv` is a simulated degradation series of RPV-S1 over
  1000 h of model time: it has no times in the calendar, so the spreadsheet gives
  only the `duration` its data cover, and the timeline does not show it.
- `environment/` holds files about the conditions of the test rather than about a
  sample: the sensor readings of the climate chamber and a simulated cell
  temperature (type `setup_log`), and a weather station's log (type
  `weather_information`).
- The project entry `project_data.archive.json` is created automatically. It
  imports the spreadsheet, writes one sample entry per sample into the folder
  `samples`, and puts the files into groups: one series per sample, with the
  standards applied to it (column `standard` of the sheet `samples`);
  `Setup logs` (the climate chamber) and `Weather information` (the weather
  station); `General` for files that belong to no sample, such as this README; and
  `Unknown` for files about a sample that name none. It plots the period that each
  file's data cover.

Edit the project data in NOMAD, or tick "fill archive from data file" in the
project entry to import the spreadsheet again. Values for the files are changed in
the spreadsheet; reprocess the upload so that the files take the changes.
