# How the SAI Conformance UI works

Status: **draft for review** · 19 Nov 2026 · describes the code in this repository as of this date.
"SAI Conformance" is a working name.

**TL;DR**

- **What it is.** A web page that sits on top of an existing set of network-switch software tests (the SAI-Challenger
  PoC). It lets anyone start those tests, watch them run, and read the results in plain words.
- **How it works.** It never runs the tests itself. It calls the project's own script, `scripts/poc/run_poc.sh`,
  exactly as a person would in a terminal, then reads the report files that script writes. Runs started from a
  terminal show up in it too, because both write to the same folder.
- **Why it exists.** Reading results today means opening XML files. The terminal also shows "known gaps" as PASSED,
  and there's no way to see who is using a target.
- **Where it stands.**
  - Reading, comparing and charting every past run works.
  - Starting runs works, but has been tested only against a stand-in script so far. The first real run from the UI
    is the next checkpoint (CP6).
  - Editing target profiles, vendor onboarding, developer tools and multi-user mode are later phases, not built.
- **What it never does.**
  - It never edits test code.
  - It never stops or starts a container.
  - It never deletes a report, and it never commits to git.

---

## Contents

1. [The basics, for someone new](#1-the-basics-for-someone-new)
2. [The goal of this project](#2-the-goal-of-this-project)
3. [How the UI works](#3-how-the-ui-works)
4. [The project steps: what, why, and why not something else](#4-the-project-steps-what-why-and-why-not-something-else)
5. [Questions a reviewer might ask](#5-questions-a-reviewer-might-ask)
6. [Reference: glossary, code map, running and configuring](#6-reference)

---

## 1. The basics, for someone new

### 1.1 Switches, SAI and libSAI

- A **network switch** moves packets between its ports. Inside it is a special chip (an **ASIC**) that does the
  moving at full speed, and ordinary software that tells the chip what to do: which ports belong to which VLAN, where
  each MAC address lives, which packets to drop, and so on.
- Every chip maker has its own way of programming its chip. **SAI** (Switch Abstraction Interface) is an open,
  common programming interface for switch chips. If the network software speaks SAI, it can drive any chip whose maker
  provides a SAI library.
- That library is called **libSAI** (`libsai.so`). Each chip vendor writes their own. The SAI specification says
  what every call must do and what status code it must return, for example "creating a VLAN that already exists must
  return `SAI_STATUS_ITEM_ALREADY_EXISTS`".
- **Conformance** means: does a given libSAI behave the way the SAI specification says?

### 1.2 Testing without hardware

- Real switches are expensive and scarce. There are software stand-ins for a switch chip, so a libSAI can be tested on
  an ordinary computer.
- **SAI-Challenger** is an open-source test framework for SAI. It talks to a libSAI through the SAI interface, runs
  tests written in Python with **pytest**, and can send real packets with the **PTF** packet library.
- **The PoC** (proof of concept) is a project built on top of SAI-Challenger by a small team. It added its own tests
  in `tests/poc/` of the SAI-Challenger checkout, a script to run them (`scripts/poc/run_poc.sh`), and one settings
  file per target (`tests/poc/targets/*.json`). It runs on one shared Ubuntu virtual machine with no switch hardware.

### 1.3 The three targets

A **target** is one libSAI set up to be tested. Each one runs in its own Docker container on the shared machine.

| Target | What it is | Forwards packets? | Tests it can run |
|---|---|---|---|
| `saivs` | SAI's own virtual switch, reached through `sairedis` (a Redis-based message layer) | No: it stores objects but moves no packets | Level 1 only |
| `saivs-thrift` | The same virtual switch, reached through `saithrift` (a remote-call layer) instead | No | Level 1 only |
| `saivpp` | A libSAI that programs FD.io VPP, a real software packet forwarder, with 16 virtual ports | Yes | Level 1 and Level 2 |

### 1.4 Tests, tracks and levels

- The PoC suite has about **87 test functions in 8 files** (count of 18 Nov 2026). Some functions run several times
  with different values (for example VLAN IDs 0, 4095 and 4096), so a full run reports more results than that.
- Tests are grouped into **tracks** by subject, marked with pytest markers:
  - Track A: `l2` (L2 forwarding and VLANs).
  - Track B: `l3` (L3 routing).
  - Track C: `acl` (access-control lists) and `counters`.
  - "Framework" tests check the PoC's own helper code, not a target.
- **Level 1** tests are control-plane tests: create, read and remove SAI objects and check the status codes.
- **Level 2** tests are traffic tests: send packets in one port and check where they come out. They carry the
  `traffic` marker and run only on a target that forwards packets (today, `saivpp`), and only when `--traffic` is
  passed.
- Some test classes are **step scenarios**: numbered steps that build on each other (step 03 needs steps 01 and 02).
  If an early step fails, later steps are skipped with "needs step(s) that did not pass".
- Tests that come from SAI-Challenger itself rather than from `tests/poc` are called **upstream** tests.

### 1.5 Target profiles and expected gaps

- Each target has a **profile**, a JSON file in `tests/poc/targets/`. It says which testbed and container to use,
  which ports the tests may use, which lock to take, and which **expected gaps** the target has.
- An **expected gap** is a place where a target is known not to follow the SAI specification. For example, `saivs`
  accepts VLAN ID 4095 although the specification says to reject it. A gap is written as
  `"test name or pattern": "reason"`:

  ```json
  "expected_gaps": {
    "test_poc_l2_vlan_invalid_id_rejected[4095]": "Target accepts VLAN ID 4095",
    "test_poc_l2_vlan_duplicate_rejected": "Duplicate VLAN returns INVALID_PARAMETER, expected ITEM_ALREADY_EXISTS"
  }
  ```

- The PoC's pytest setup (`tests/poc/conftest.py`) marks every test that matches a gap as **strict xfail**: "this
  test is expected to fail, and it is an error if it passes".
  - If it fails, pytest records it as an expected failure, and the run stays green.
  - If it passes, pytest records it as a failure (`[XPASS(strict)]`), because the recorded gap is no longer true and
    should be removed.
- The project's main rule: **tests follow the SAI specification, and nothing target-specific goes into test code.**
  Every difference between targets lives in the profiles, as strict xfail. A test never says "if this is saivpp, do
  something else".

### 1.6 How a run happens today, from a terminal

```
scripts/poc/run_poc.sh saivs poc_<user>              # every PoC test on saivs
scripts/poc/run_poc.sh saivpp poc_<user> --traffic   # include Level 2 traffic tests
```

`run_poc.sh` does the following, in order:

1. Reads the target's profile to learn the testbed, the lock name and the container options.
2. Waits for the target's **lock**, a file under `/opt/sai-poc/locks/` held with `flock`. Only one run per target at a
   time, so two people never disturb each other's switch state.
3. Runs pytest inside the target's container through SAI-Challenger's `exec.sh`. Your copy of `tests/poc` is
   mounted in the container as `poc_<user>`.
4. Writes two reports into `tests/poc/reports/`: `<target>-<MMDD-HHMMSS>.xml` (JUnit XML, machine-readable) and
   `.html` (pytest-html, human-readable).
5. Prints `report: …/<target>-<stamp>.{html,xml}  exit=<code>` and exits with pytest's exit code.

There is also `tests/poc/summarize.py`, which reads the XML files and prints a comparison table of the targets.

### 1.7 What is hard about that today

- You wait on a lock you can't see. Nothing tells you who holds it or since when.
- The terminal shows an expected gap as **PASSED** (a reporting hook in the conftest does this on purpose). To find
  the gaps you have to read the XML.
- Recording a gap means editing JSON by hand.
- Comparing targets means running `summarize.py` and reading its table.
- Failure messages are raw pytest tracebacks. Working out "did the target return the wrong status, or did my test
  break?" takes experience.
- A chip vendor with their own `libsai.so` can't test it at all: each target's libSAI is built from source inside its
  container image.

---

## 2. The goal of this project

### 2.1 The end goal

> One purpose-built web UI where anyone can run the SAI conformance tests on a target, read every result in plain
> words, keep the target's expected gaps up to date, compare targets, and hand over a conformance report, without
> breaking any of the PoC's rules.

### 2.2 Who it is for

| User | The question they bring |
|---|---|
| A developer on the project | Did my tests pass on all three targets? Is this failure a gap in the target or a bug in my test? Is my branch ready? |
| A libSAI vendor (later phase) | Does my library meet the SAI specification? Where does it differ? Give me a report I can hand over. |
| A mentor or reviewer | Is every result traceable to a report file? Which gaps exist, with what reason? |
| Whoever looks after the shared machine | What is running where, who holds which lock, is there memory to spare? |

### 2.3 What "done" looks like

Each phase has an exit check (section 4). The most important ones:

- A run started from the UI gives **the same JUnit results** as the same command typed in a terminal.
- The UI's target comparison gives **the same results as `summarize.py`** on the same report files.
- Adding a gap from the UI turns that test into an Expected gap on the next run, and removing it brings the old result
  back.
- A vendor's library (stood in for by `libsaivs.so`) can be onboarded end to end and produce a conformance report.

### 2.4 Rules the UI must never break

1. **Tests run only through `run_poc.sh`.** The UI never calls pytest or `exec.sh` itself, so the lock is always
   taken and the reports always land in the usual place.
2. **No target-specific logic in tests.** The UI has no code editor and no way to write into test files. Gaps go only
   into profiles, and only as strict xfail.
3. **Nothing free-text reaches a command line.** The UI sends only choices (a target name, a preset, test names from
   its own catalogue), and the server builds the command from values it already knows.
4. **The shared testbed is not touched.** The UI never starts, stops or removes a container and never kills a process
   inside one.
5. **No deletes, no git.** It never deletes a report or a capture file and never commits or pushes.
6. **Anything that leaves the team is a draft.** Exported reports carry a "draft for review" label.

---

## 3. How the UI works

### 3.1 The big picture

```
 ┌───────────────────────────── your browser ─────────────────────────────┐
 │  React web app (web/): Targets · Runs · Compare · Tests · run sheet    │
 │  asks the server for JSON every 1–10 s; sends only choices             │
 └───────────────▲──────────────────────────────────┬─────────────────────┘
                 │ JSON over HTTP (127.0.0.1 only)   │
 ┌───────────────┴──────────────────────────────────▼─────────────────────┐
 │  Python server (server/): FastAPI app (api/) + plain-Python core/      │
 │    reads:  profiles, test files, report files, docker ps, /proc/locks  │
 │    starts: scripts/poc/run_poc.sh  (list of arguments, no shell)       │
 │    keeps:  its own run records, console logs, gap kinds                │
 └──────┬──────────────────────────────┬──────────────────────────┬───────┘
        │ reads                        │ starts                   │ writes
        ▼                              ▼                          ▼
 SAI-Challenger checkout        run_poc.sh ── flock ── exec.sh    ~/.local/state/sai-challenger-ui/
  tests/poc/test_*.py                  │                           ~/.config/sai-challenger-ui/
  tests/poc/targets/*.json             ▼
  tests/poc/reports/*.xml ◄── pytest inside the target's Docker container
```

The key idea: **the reports folder is the single source of truth.** Every run, from the terminal or the UI, ends up
as an XML file there, and the UI builds everything it shows from those files.

### 3.2 The three layers

| Layer | Folder | What it does | Built with |
|---|---|---|---|
| Web app | `web/src/` | Draws the pages, keeps filters and selections, asks the server for data | React, TypeScript, Vite, TanStack Router and Query, Radix |
| API | `server/sai_challenger_ui/api/` | Answers `/api/...` requests, checks that actions come from this machine, serves the built web app | FastAPI and uvicorn |
| Core | `server/sai_challenger_ui/core/` | All the real logic: reading reports, the catalogue, profiles, the queue, history, causes, gates, exports | Python standard library only |

The core uses only the Python standard library on purpose. It can be tested on any machine, and the only extra
packages needed are the web server itself (FastAPI, uvicorn) and the test tools (pytest, httpx).

### 3.3 What it reads and what it writes

| Where | Read or write | What |
|---|---|---|
| `tests/poc/test_*.py` in the checkout | Read | The test catalogue (read as text, never imported or run) |
| `tests/poc/targets/*.json` | Read | Profiles: ports, lock, expected gaps |
| `tests/poc/reports/*.xml`, `*.html` | Read | Every run's results |
| `tests/poc/reports/` | Written **by `run_poc.sh`**, not by the UI | The reports of runs the UI started |
| `docker ps -a` | Read | Is each target's container running? |
| `/proc/locks`, `/proc/<pid>/` | Read | Who holds each target's lock, and since when |
| `/proc/meminfo` | Read | Free memory on the machine |
| `git` in the checkout | Read | Commit, branch and changed files, recorded with each UI run |
| `~/.local/state/sai-challenger-ui/jobs/` | Write | One `.json` record and one `.log` console file per UI run, plus `runner.lock` |
| `~/.config/sai-challenger-ui/gap_notes.json` | Write | The kind of each expected gap (Limitation, Known bug, Temporary), when someone sets one |
| `~/.config/sai-challenger-ui/gates.toml` | Read (you write it, if you want it) | Your own conformance gate rules |
| `~/.config/sai-challenger-ui/target_facts.toml` | Read (optional) | Override of "does this target forward packets" |
| The browser's local storage | Write | The theme and small view preferences (layout, grouping, console drawer open) |

### 3.4 From a report file to six plain words

pytest's own words (passed, failed, error, skipped, xfail, xpass) are confusing for a newcomer, and the terminal even
prints an expected gap as PASSED. The UI turns every result into one of six words, used on every page:

| UI word | Shape | Meaning | What the JUnit XML says |
|---|---|---|---|
| **Pass** | ● | The target did what the SAI specification says | No `<failure>`, `<error>` or `<skipped>` |
| **Fail** | ■ | It didn't, and no expected gap is recorded | `<failure>` |
| **Setup error / Cleanup error** | ▲ | The test couldn't start or couldn't clean up. Not a verdict on the target | `<error message="failed on setup…">` / `"failed on teardown…"` |
| **Expected gap** | ◆ | Failed as the profile says it would; the reason is shown | `<skipped type="pytest.xfail">` |
| **Gap now passes** | ◇ | A recorded gap passed: the gap is out of date and should be removed | `<failure message="[XPASS(strict)] …">` |
| **Skipped** | ○ | Not run on purpose; the reason is shown | `<skipped>` of another kind |

The rules live in `core/junit.py` and `core/vocab.py`. Three details matter:

- **Errors are kept apart from failures.** `summarize.py` counts both as "failed". The UI doesn't, because a broken
  fixture says nothing about the target. For the parity check with `summarize.py`, errors are counted as Fail.
- **One test written twice.** When a test fails and its cleanup also fails, pytest writes it twice. The UI keeps the
  worse result, notes "cleanup also failed", and adds the times.
- **Upstream tests** (not under the `poc_<user>` mount) never have expected gaps applied.

### 3.5 Finding runs

- Every file named `<target>-<stamp>.xml` in the reports folder is one run (`core/reports.py`). Files with other names
  (scratch files, captures) are ignored.
- Today's stamps have no year (`saivpp-1117-103309`). The run time comes from the timestamp inside the XML. If that is
  missing, the year comes from the file's date, so a December stamp on a January file counts as last year. Stamps that
  include the year (`saivpp-20261118-140200`) are read too, ready for the planned change to `run_poc.sh`.
- A target name with a dash (`saivs-thrift`) is matched against the known profile names, longest first, so it isn't
  mistaken for `saivs`.
- Files are parsed once and parsed again only when they change. The folder is checked for new files at most once a
  second. A half-written or broken file is listed as a problem and never breaks the history.
- A run is labelled **UI** if the UI started it (its run record names that report) and **CLI** otherwise.

### 3.6 Knowing the tests: the catalogue

The run sheet needs a list of tests to pick from, and the pages need a readable title for each test.
`core/catalog.py` builds it by **reading the test files as text** with Python's `ast` module. Nothing is imported
and nothing is run. From each test it takes:

- module, class and function name, and the line number;
- markers (`l2`, `l3`, `acl`, `counters`, `traffic`, `negative`), and from them the track, the level (L1 or L2
  traffic) and the kind (positive or negative);
- the docstring, shown as "What it checks";
- parameter values, when they're written in the file. When they come from a data file instead, the IDs are taken from
  past reports;
- for step scenarios, each step's name and the steps it needs (`@step(..., needs=[...])`);
- the largest number of ports it asks for (`poc_ports(n)`).

A **readable title** is made from the name: `test_poc_l3_vrf_create_readback` becomes "VRF create and read back", and
`test_poc_acl_drop_06_drop_port_is_dropped` becomes "Step 06: drop port is dropped". The full pytest ID is always
shown beside it.

### 3.7 Knowing the targets

- **Profiles** (`core/profiles.py`) are read, never written. The gap-matching rule is a copy of the conftest's rule:
  shell-style patterns where `*` and `?` are wildcards and `[` is literal, so `name[4095]` matches only that
  variant. The first pattern that matches wins. A test proves the copy gives the same answer as the conftest on every
  real profile entry.
- **Does the target forward packets?** No profile says so yet. Until a `forwards_traffic` key is agreed, the UI reads
  it from its own `target_facts.toml` (saivpp: yes; saivs and saivs-thrift: no). Once the profile carries the key,
  the profile wins.
- **Container state** (`core/testbed.py`) comes from `docker ps -a`, called at most every 3 seconds. The container
  name is worked out the same way `exec.sh` does it (`sc-<asic>-<target>-run`, or `sc-thrift-…` for thrift).
- **Who holds the lock.** Linux lists every held file lock in `/proc/locks`. The UI finds the entry for the target's
  lock file, then reads that process's details from `/proc/<pid>/`: the user, the start time and its command line. The
  `--junitxml=poc_<user>/reports/<run>.xml` argument tells it whose run it is. That gives "Busy: <user>'s CLI run since
  14:02 · 1 waiting".
- **One state per target**, merged from all of the above: Can't reach Docker, Container stopped, Busy (someone else),
  Busy (your CLI run) or Ready.

### 3.8 Starting a run, step by step

```
 Run sheet (browser)          Server                                     Shared machine
 ───────────────────          ──────                                     ──────────────
 1 pick targets, what to run,
   options ─────────────────► 2 /api/plan: build the command,
                                 count tests and gaps, estimate time
   preview + "Show command" ◄─┘
 3 Run ─────────────────────► 4 /api/jobs: check the request comes from
                                 this machine; plan again; record commit,
                                 branch and changed files; queue one job
                                 per target (× Repeat)
                              5 scheduler (every ≤ 2 s): for each lock,
                                 if no UI run uses it and /proc/locks shows
                                 nobody holding it, start the oldest job ──► run_poc.sh <target> <args>
                                                                             (own session; output →
                                                                              jobs/<id>.log)
                                                                                 │ flock, exec.sh, pytest
 6 live page polls every 1 s ◄─ read the console log, map lines to words ◄──────┘
                              7 process ends: read run_poc.sh's last line
                                 for the report name; check the .xml exists
 8 page switches to the
   finished run ◄───────────── 9 /api/runs/<run id> reads the XML
                             10 Retry failures on? queue a rerun of only
                                 what failed (back to step 5)
```

In more detail:

1. **The run sheet** (`web/src/RunSheet.tsx`) sends only choices:
   - one or more targets, from the profile names;
   - what to run, one of four presets:
     - **Full PoC suite**;
     - **Tracks** (L2, L3, ACL, Counters: a fixed list, passed as `-m "l2 or l3"`);
     - **Last run's failures**;
     - **Pick tests…**, from a Track › file › test tree;
   - traffic on or off; MLD filter auto, on or off; Repeat 1 to 5; Retry failures off or 1 to 3; Notify me when done
    (a browser notification when the run ends).
2. **Planning** (`core/selection.py`) turns the choices into `run_poc.sh` arguments:
   - Picked tests become pytest node IDs (`poc_<user>/test_poc_l2.py::test_x[0]`), sorted into file order. When
     every test of a file is picked, the file is passed instead.
   - If a picked scenario step needs earlier steps, those are added, with a note saying so.
   - `--traffic` is added only if the target forwards packets and traffic is left on. Otherwise a sentence explains
     why the traffic tests will be skipped.
   - The MLD choice is passed only when traffic tests will run, because only they are affected by it.
   - The plan also counts the tests, counts how many the profile records as gaps, and estimates the time: each test's
     most recent duration on that target, the median for tests never seen, plus 15 seconds for start-up.
   - **Show command** prints the exact line, which works the same when typed in a terminal.
3. **Queueing** (`core/jobs.py`). There is one queue per lock. A job waits while another UI run uses its lock or while
   anyone else holds it. It can be taken off the queue at any time before it starts.
4. **Launching.** `run_poc.sh` is started with a list of arguments, never through a shell. It runs from the checkout,
   in its own process session, with its output going to `~/.local/state/sai-challenger-ui/jobs/<job id>.log`.
   `run_poc.sh` still takes the lock itself. The UI only waits its turn first.
5. **Surviving a restart.** Because the run has its own session, stopping the UI server (Ctrl+C) doesn't stop the
   test run. A restarted server finds the run by its process ID and follows it again. Jobs that were only queued are
   dropped, with the note "Nothing was run", so nothing starts that nobody is watching for.
6. **One owner.** Only one UI server per state folder may start runs. It holds `runner.lock`. A second server started
   by mistake shows the runs read-only.

### 3.9 Following a live run

While a run is going, the only live source is the console text, because `run_poc.sh` writes no event file yet.
`core/console.py` reads pytest's `-v` lines:

- `Waiting for the saivs lock...` → waiting for the lock.
- `collected 64 items / 5 deselected` → how many tests will run.
- `poc_<user>/test_poc_l2.py::test_x[0] PASSED [ 12%]` → one finished test.
- A node ID alone on the last line → the test running now.

Two console words are read with the profile in mind:

- **PASSED with a reason in brackets, or on a test the profile records as a gap**, means Expected gap. The conftest
  prints strict xfail as PASSED.
- **FAILED on a test the profile records as a gap** means Gap now passes.

The live view is provisional. Durations, failure messages and source lines aren't known until the XML file is read.
The web app polls every second; the console is re-parsed only when the log file has grown.

### 3.10 When a run ends

1. The job is marked done. The report name comes from `run_poc.sh`'s last line (`report: … exit=<code>`), or earlier
   from the `--junitxml=` argument of the process holding the lock.
2. If no XML exists, the job notes "No report was written", and the console shows why. Typical causes are a
   collection error or an interrupted script.
3. The live page sees the report and switches to the finished run page, which reads the XML. **From here on the JUnit
   file is the final word.**
4. **Retry failures**, if chosen: the server collects the tests that ended as Fail, Setup error or Cleanup error (not
   Gap now passes, not upstream tests, not collection errors) that the catalogue still knows. It queues a new run of
   only those, through `run_poc.sh` again, labelled "Retry 1 of 2". A test that passes on a retry is marked
   **Retried**. Retries happen only for runs the server watched to the end, never after a restart.

### 3.11 What the server works out from the results

Everything below is computed from the report files on each request. Nothing is stored except gap kinds.

| What | How it is worked out | Code |
|---|---|---|
| **Headline** | One sentence: what needs attention first ("2 tests fail · 1 setup error"), else "Pass except 4 expected gaps", else "Pass" | `vocab.headline` |
| **Plain words** | "The target returned SAI_STATUS_INVALID_PARAMETER. The SAI spec expects SAI_STATUS_ITEM_ALREADY_EXISTS." Read from pytest's assertion text and diff, packet messages, or a single status in the message | `explain.what_happened` |
| **Hint** | A known failure signature (a regular expression) mapped to one line of advice, for example "Objects left from an earlier run". There are 9 today, in `hints.toml`; the team adds more as it learns | `explain.Hints` |
| **Expected and actual** | When the message has both values, the "Show difference" view compares them (unified or side by side; by characters, words or lines) | `explain.expected_actual`, `DiffModal.tsx` |
| **Since the previous run** | New failures and fixed tests against the newest earlier run on the same target that ran any of the same tests | `reports.since` |
| **Transitions** | New (first run of this test on this target), Fixed (Pass now, Fail, error or Expected gap before), Regressed (Fail now, not before), New error (an error now, not before) | `history.transition` |
| **Flaky** | Takes the test's last 10 results on this target, ignoring runs that skipped it or didn't select it, and forgets everything before 5 identical results in a row. If the outcome changed at least twice and the test is failing now, it is Flaky. This is Allure Report 3's rule, except that runs which didn't select the test are left out, because PoC runs often pick one track | `history.flaky` |
| **Age** | How many runs in a row the test has had this same result, and since when | `history.marks` |
| **Causes** | Failures and gaps grouped by why they happened, in two families: target behaviour (Fail, Expected gap, Gap now passes) and test or setup problems (errors). The cause is, in order: a hint's title, a packet that did or didn't arrive, "accepts what the spec refuses", the SAI status named, else the message's first line | `causes.py` |
| **Gates** | Rules a run must meet. The defaults: no Fail, no Gap now passes, no setup or cleanup errors, the full suite ran, every gap is in the profile, no test over 120 s. Two more types are available (all tracks ran; a minimum pass rate). Replace them with your own `gates.toml`. Gates change nothing in how `run_poc.sh` exits | `gates.py` |
| **Gap status** | For each gap in a profile against a run: Still fails, Now passes, Not run in this run, Recorded but reported as Fail, Mixed results. Warnings: matches no test; listed twice in the file | `profiles.gap_statuses` |
| **Unrecorded gaps** | An expected failure that no profile pattern explains, meaning someone called xfail inside a test, which the rules forbid. Shown as a warning, never hidden | `profiles.unrecorded_gaps` |
| **Gap kind** | Limitation (the default), Known bug (with a link), or Temporary (with a review date; overdue after it). Kept in the UI's `gap_notes.json`, never in a profile | `gapnotes.py` |
| **Pass rate** | Pass divided by the tests that ran (Skipped left out; gaps and errors count as not passing). Shown in the centre of the donut | `exports.pass_rate`, web |
| **Trends** | Per run, for up to 20 runs on the target: counts by result, fixed and regressed counts, run time | `history.dynamics` |
| **Stability by track** | Share of tests whose result didn't change over their last 10 results | `history.stability` |

### 3.12 The pages

The top bar has four sections, **Targets · Runs · Compare · Tests**. It also holds an activity chip showing UI runs
that are queued or running, and the light or dark theme switch.

**Targets** (home)

- One card per target, showing:
  - its state (Ready, Busy with who and since when, Container stopped);
  - the newest run, as a donut with the pass rate, counts by result and the result strip (one small cell per test,
    coloured and shaped by result);
  - the last 12 runs as small bars;
  - the gate result;
  - a Run button.
- A banner appears if Docker can't be reached, and a memory chip if free memory is low.

**Run sheet**

- Slides in over the current page, already filled in from where it was opened.
- Shows the plan before you start: how many tests, how many are expected gaps, how many need traffic, roughly how long
  it will take, and the exact command.

**Live run** (`/jobs/<id>`)

- Queued: who or what it is waiting for.
- Running: tests dropping into their result groups as they finish, the test running now, and a console drawer with
  the raw output.
- A queued run can be taken off the queue. There is no Cancel once it has started (see section 4, step 0.10).

**Run page** (`/runs/<run id>`), the core page, the same for CLI and UI runs.

- The header shows:
  - the donut and the headline;
  - the container, the number of tests and which run it was compared with;
  - a **Results / Charts** switch;
  - **Rerun**: failed only, everything that needs attention, the same tests, or the full suite. Each one opens the
    run sheet already filled in;
  - **Export**: the conformance report (open or download), the Markdown summary (copy or open), and the files
    `run_poc.sh` wrote (pytest HTML, JUnit XML, and the console log for a UI run).
- **Results tab:**
  - a stats row and the result strip, with chips for changes against earlier runs;
  - search, and filters for Flaky, Transition, Cause and Gap kind;
  - Group by Result (the default, problems first), Track or File;
  - Sort by run order, status, duration or name;
  - a tree with a proportional bar on each group;
  - split layout (list and detail side by side) or full width;
  - `j`/`k` to move between tests and `/` to search.
- **Causes tab:** the groups from section 3.11.
- **Gates tab:** each rule with actual against expected, and the tests that break it.
- **Run log tab:** the console of a UI run.
- **Charts view:**
  - current status;
  - status over the last runs;
  - fixed and regressed per run;
  - stability by track;
  - run time;
  - test durations.

**Test detail** (inside the Run page)

- The readable title and the full test ID with a copy button. Previous and next ("14/93").
- **Overview tab:**
  - the result with its message;
  - "Show difference" when both values are known;
  - the hint;
  - retries;
  - labels (markers, file, class, parameter, gap pattern, level, kind);
  - "What it checks" (the docstring);
  - the scenario's steps;
  - five lines of source around the failing line.
- **History tab:** this test on this target over past runs, "passed n of m".
- **Targets tab:** the same test on every target.
- **Rerun this test.**

**Runs**

- Every run, newest first, grouped by day, with a result bar.
- UI runs that are running or queued appear at the top.
- Filter by target, or show only runs that need attention.

**Compare**

- **Matrix:**
  - tests down the side, targets across the top, each cell a result;
  - above it, a heat map of pass rate by track and target;
  - "only rows that differ".
- **Run diff:** any two runs, even on different targets, over the tests both ran: new failures, fixed, gaps that now
  pass, new expected gaps, gaps removed, became skipped, no longer skipped, reason changed.
- **Gaps:** every expected gap on every target, with its reason, its status in the newest run and its kind. The
  kind can be edited here.

**Tests**

- The catalogue as a Track › file › test tree.
- Each test shows its newest result on every target.
- The detail pane shows the docstring, the labels (track, file and line, level, kind, markers) and the test's recent
  results on each target.

**Exports**

- **Conformance report:** a single self-contained HTML file, always in the light theme, with fonts embedded. It
  contains the summary, the charts, every test and its result, and the expected gaps with reasons. Its footer says it
  is a draft to be reviewed before it is sent.
- **Markdown summary:** a short text of the run and its failures, with messages and hints. It is made to paste into a
  review or an AI coding assistant.

### 3.13 Safety: who can do what

- The server listens on `127.0.0.1` by default, so only this machine can reach it.
- Starting a run, taking one off the queue, and saving a gap kind are all refused unless:
  - the server is in local mode;
  - the request carries the header `X-SAI-Challenger-UI: 1`. A web page on another site can't add this header
    without a browser pre-check, which the server never answers;
  - the `Host` and `Origin` say localhost, which defeats DNS-rebinding tricks;
  - the body is JSON.
- Run IDs, job IDs and test keys are looked up in what the server already knows. Nothing from a request is used as a
  file path or passed to a shell.
- **Limit:** anyone logged in to the same machine can still reach `127.0.0.1`. Logins and roles come with shared mode
  (Phase 5).

### 3.14 The look, and why

- **After Allure Report.** On 19 Nov 2026 the plain first look was replaced by one modelled on Allure Report 3, a
  widely used open-source test report: cards with soft shadows, donuts, trees with proportional bars, split views and
  charts. Allure is Apache-2.0 licensed. Its layout and colours were copied; its logo and name were not.
- **Fonts:** PT Root UI and JetBrains Mono, both under the SIL Open Font Licence, bundled in `web/src/fonts` so the UI
  works offline. Programming ligatures are switched off, so `!=` in test source reads as written.
- **Colours mean results, nothing else:**
  - Pass green;
  - Fail red;
  - Setup or Cleanup error yellow (Allure's "broken");
  - Expected gap sky blue;
  - Gap now passes violet;
  - Skipped slate.

  The palette was checked with a colour-vision validator. The light-mode violet was darkened because it sat too close
  to the sky blue.
- **Shape as well as colour** (● ■ ▲ ◆ ◇ ○), so results read correctly in greyscale and for colour-blind readers.
- **Dark by default**, with a fully designed light theme one click away. Exports are always light.

---

## 4. The project steps: what, why, and why not something else

### 4.1 How the plan is organised

- Six **phases**, 0 to 5, each split into numbered **steps** (0.1, 0.2 and so on).
- Fourteen **checkpoints** (CP0 to CP13). At each one, work stops until the project owner has seen the result and
  agreed to go on.
- Any step that would touch the shared testbed (start, stop or build a container, or act inside one) is asked about
  each time, even if something similar was agreed before.
- Steps that would change the SAI-Challenger repository (the shared test code) wait for the owner's request. This is
  why most of Phase 0 is on hold and the UI was built to work with today's unmodified scripts.

For each step below: **What** it is, **Helps** (how it moves us towards the goal), **Why this way** (and why not
another option), and **Status** on 19 Nov 2026.

### 4.2 Why these phases, in this order

| Phase | Delivers | Why it sits here |
|---|---|---|
| 0 Groundwork | Small, opt-in changes to `run_poc.sh` and the conftest so a UI can follow a run exactly | The UI must reuse the same script and the same gap rule, never a copy that drifts. These changes come first because everything later depends on them, and they are invisible to terminal users |
| 1 Core loop | Targets, run sheet, live run, run page, run history, adding and removing gaps | Nothing else is useful until you can start a run and read it. This is the smallest UI that beats the terminal |
| 2 Compare and reports | Target matrix, run diff, gap register, test catalogue, conformance and coverage reports | The team needs comparison every day. It only needs the reports folder, so it carries little risk |
| 3 Vendor onboarding | Upload a `libsai.so`, build a target around it, run the baseline and the suite | Highest value for outsiders, but it rests on an unproven assumption (see 3.0), so it waits until the parts it reuses are solid. Its risky spike starts early, alongside Phase 1 |
| 4 Developer tools | "Is my branch ready?" checks, a new-test scaffold, test data forms, the definition-of-done list | Conveniences on top of a working core. They help the team but nobody is blocked without them |
| 5 Shared mode | Logins, roles, a queue across users, admin-only container control, reservations | Needs decisions with the mentor (which account the UI runs as, how people log in) and possibly a container restart. Last, because it changes the shared machine |

**Orders that were considered and not chosen:**

- **(a) Vendor onboarding before compare.**
  - **Risks:** it builds on the unproven ABI question (3.0); if that fails, the phase is wasted.
  - **Cost:** the team waits longer for the comparison it needs now.
  - Not chosen.
- **(b) Shared mode early, so the whole team uses one instance.**
  - **Risks:** it touches the shared machine before the UI is proven, and needs a service account and a container
    restart.
  - **Cost:** decisions and approvals before any feature exists.
  - Not chosen.
- **(c) Only improve the terminal tools** (a better `summarize.py`, a lock-status command).
  - **Risks:** none to the testbed.
  - **Cost:** it fixes reading, but not the gap round trip, the live view or vendor onboarding.
  - Kept as the fallback.
- **(d) Use Allure Report itself** (add `allure-pytest` to the test containers).
  - **Risks:** it changes SAI-Challenger and the container images. How Allure shows strict xfail and XPASS(strict) isn't
    stated in its documentation; if they appear as Skipped and Failed, Expected gap and Gap now passes lose their
    meaning.
  - **Cost:** the run control, queue and gap editing would still have to be ours.
  - Not chosen: we copied the look instead.

### 4.3 Phase 0: Groundwork

Goal: the existing scripts give a UI what it needs, while the terminal keeps working exactly as before.

**0.1 Install the tools**

- **What:** a Python virtual environment for the server; Node.js to build the web app.
- **Helps:** nothing can be built without them. The shared machine had no `pip`, no working `venv` and no Node.
- **Why this way:**
  - **(a) User-local tools in the home folder (`uv`, a Node tarball). Chosen.**
    - **Risks:** downloads binaries onto the shared machine.
    - **Cost:** about 300 MB in one home folder; nothing shared changes.
  - **(b) Ask an admin to `apt install` the packages.**
    - **Risks:** needs sudo, and Ubuntu's packaged Node is too old for current Vite anyway.
    - **Cost:** one request, then a wait.
  - **(c) Build the web app in a throwaway container.**
    - **Risks:** a new container on a shared, memory-tight machine.
    - **Cost:** the most moving parts.
- **Status:** Done, 18 Nov 2026 (uv 0.13.9, Node 24.22.3, Playwright 1.65.1 for screenshots).

**0.2 Where the code lives**

- **What:** the plan was a `ui/` folder on a branch of SAI-Challenger.
- **Helps:** gives the work a home.
- **Why this way:** the owner decided on 18 Nov to build the UI in **its own repository** (this one) and to change
  SAI-Challenger only on request. The shared test repository stays free of UI code until the team agrees, and the UI
  finds the checkout through a path setting.
- **Status:** Done differently: this repository.

**0.3 A shared gap rule (`tests/poc/lib/profile.py`)**

- **What:** move "does this test match this gap pattern?" out of the conftest into a small module both the conftest
  and the UI import.
- **Helps:** the UI and pytest can never disagree about which tests are gaps.
- **Why this way:** a copy would drift. Importing the conftest itself isn't possible on the host, because it needs the
  SAI framework.
- **Status:** On hold (it changes SAI-Challenger). Meanwhile the UI keeps a copy in `core/profiles.py`, and a test
  checks it against the conftest's rule on every real gap entry.

**0.4 Optional settings for `run_poc.sh`**

- **What:**
  - overridable paths and mount name;
  - a run ID set from outside;
  - the year in report names;
  - the console saved to a `.log` file;
  - `POC_LOCK_WAIT=0`, which reports "busy" at once with exit code 75 instead of waiting.
- **Helps:** the UI would know a run's report name before it starts, could tell "busy" from "failed", and would keep a
  log next to the report.
- **Why this way:** every setting is opt-in, so terminal users see no change. The alternative, a separate UI-only run
  script, would break the "only through `run_poc.sh`" rule.
- **Status:** On hold. The UI works without it:
  - it learns the report name from the running process's `--junitxml=` argument;
  - it reads the lock holder from `/proc/locks` before starting;
  - it keeps its own console log in its state folder.

**0.5 A live event file**

- **What:** an opt-in conftest hook that writes one JSON line per test phase (outcome, gap reason, duration, captured
  output) when `POC_EVENTS` is set.
- **Helps:** an exact live view, including expected gaps, which the terminal prints as PASSED.
- **Why this way:** the console is meant for people; an event file is meant for programs. The hook is not
  target-specific, so it is allowed under the rules.
- **Status:** On hold. The UI reads the `-v` console lines instead (section 3.9), and the XML file confirms everything
  at the end.

**0.6 Commit the helper scripts**

- **What:** three personal helper scripts (add a gap, print the gap table, compare runs) become modules under
  `scripts/poc/`, where the runbook already says they are.
- **Helps:** the UI and people use the same helpers.
- **Status:** On hold.

**0.7 A `forwards_traffic` key in profiles**

- **What:** `"forwards_traffic": true` for saivpp, `false` for the others. The conftest ignores it.
- **Helps:** "Level 2 only on saivpp" is a fact about the target, so it belongs in the profile. Today it lives only in
  the documentation.
- **Status:** On hold. The UI reads `target_facts.toml` until the key exists.

**0.8 Building the test catalogue**

- **What:** a list of every test, with markers and parameters.
- **Why this way:**
  - **(a) `pytest --collect-only` through `run_poc.sh`.**
    - **Risks:** it takes the lock and runs in the container.
    - **Cost:** small.
  - **(b) A host environment with the SAI framework installed.**
    - **Risks:** it is not the environment the tests really run in.
    - **Cost:** heavy.
  - **(c) Read the test files as text with `ast`, and fill parameter IDs from past reports. Chosen in practice.**
    - **Risks:** none to the testbed.
    - **Cost:** parameter values taken from data files are known only once a report has named them.
  - (c) needs no lock, no container and no change to SAI-Challenger.
- **Status:** Done as (c), `core/catalog.py`.

**0.9 Lock holder probe**

- **What:** who holds a target's lock, since when, running what.
- **Helps:** "Busy: <user>'s CLI run since 14:02" instead of a silent wait.
- **Why this way:**
  - `/proc/locks` plus `/proc/<pid>/` needs no root and no extra tool.
  - `lslocks` would also work, but adds a dependency.
- **Status:** Done (`core/testbed.py`).

**0.10 Cancel spike**

- **What:** find a safe way to stop a run. Killing the `docker exec` client on the host does **not** stop pytest
  inside the container.
- **Helps:** a Cancel button.
- **Why this way:** the proposed method stops only that run's pytest, matched by its unique report path, then does
  the clean-up `run_poc.sh` does. It acts inside a shared container, so it needs a read-only study first and sign-off
  before one trial.
- **Status:** Not started. Cancel stays disabled, and the UI says why.

**CP1–CP4:** On hold with the steps above.

### 4.4 Phase 1: Core loop (local mode)

Goal: run, read and record gaps from the browser, on your own checkout, for all three targets.

**1.1 Server skeleton**

- **What:**
  - the FastAPI app;
  - settings from environment variables;
  - `/api/health`;
  - the built web app served from the same port;
  - bound to `127.0.0.1`;
  - the `sai-challenger-ui` command.
- **Helps:** one command starts everything; no Node is needed where it runs.
- **Why this way:**
  - **FastAPI:** the PoC is Python, so the server can reuse its rules; it handles background subprocesses well; and
    it is small.
  - **Run records as JSON files rather than SQLite:** the reports folder already is the run history, so the UI only
    keeps a small record per UI run. Plain files need nothing beyond the standard library and are easy to inspect.
    SQLite may still be needed for shared mode's audit log and cross-user queue.
- **Status:** Done. The planned `install.sh` is not written yet; setup is in the README.

**1.2 Report importer**

- **What:** read every JUnit file into the six words (section 3.4).
- **Helps:** every past run, from the terminal or the UI, appears with no import step.
- **Why this way:** reading the files where they are keeps the UI and the terminal in step. A database copy could
  go stale.
- **Status:** Done. Per-run counts equal `summarize.py`'s on every report in the folder (348 runs on 19 Nov), with
  errors counted as Fail for the comparison.

**1.3 Catalogue service**

- **What:** the catalogue from 0.8, with readable titles, tracks, levels and step scenarios.
- **Status:** Done.

**1.4 Job runner**

- **What:** the queue per lock, starting `run_poc.sh`, following it, recording commit and options (section 3.8).
- **Helps:** runs from the browser, with the same lock and the same reports as the terminal.
- **Why this way:**
  - An in-process queue suits a handful of long runs; Celery or Redis would be heavy for this.
  - The UI waits its turn before starting, so a run waiting behind someone's terminal run can still be taken off the
    queue.
- **Status:** Built and unit-tested against a stand-in `run_poc.sh`. **CP6, the first real run from the UI compared
  with the same command in a terminal, waits for the owner.**

**1.5 Profile service (writing gaps)**

- **What:** add, remove and edit gaps; out-of-scope items; Undo.
  - Keep the file's exact format, so adding a gap is a one-line diff.
  - Refuse to save over a file changed elsewhere.
- **Helps:** "act where you see the problem": Add expected gap on a failed row, Remove gap on a gap that now passes.
- **Why this way:** forms over files, so nobody edits JSON by hand. The server writes the file and keeps key order and
  unknown keys.
- **Status:** Not started. It writes to SAI-Challenger, so it comes after CP6 and with the owner's go-ahead.

**1.6 Hints**

- **What:** known failure signatures mapped to one line of advice (section 3.11).
- **Why this way:** TOML rather than YAML, because Python reads TOML without extra packages.
- **Status:** Done, 9 signatures. A test checks each one against a real message from the reports where one exists.

**1.7 Look first (CP5)**

- **What:** colours, fonts, glyphs and the result strip, agreed on one static page before any screen was built on
  them.
- **Helps:** the look was settled once, and not argued over on every screen.
- **Status:** CP5 passed 18 Nov 2026. Replaced on 19 Nov by the Allure look (4.9).

**1.8 Targets page**

- **Status:** Done.
- Container Start, Stop and Restart were **not built**: on the shared machine they belong to the admin (Phase 5).

**1.9 Run sheet**

- **Status:** Done, four presets. The "upstream baseline" preset is shown as coming later.

**1.10 Live run page**

- **Status:** Done, from the console (section 3.9). Not yet done:
  - the packets panel (capture summaries);
  - the export zip;
  - Cancel (0.10).

**1.11 Runs page**

- **Status:** Done.

**1.12 Target page with gap editing**

- **Status:** Not started; needs 1.5.

**1.13 End-to-end tests**

- **What:** browser tests on saivs through the UI, forcing every result type with a temporary gap in your own
  checkout.
- **Status:** Not started; needs real runs.

**CP7, the Phase 1 exit:** the gap round trip from the UI. Not reached.

### 4.5 Phase 2: Compare and reports

**2.1 Matrix**

- **What:** the UI form of `summarize.py`: tests by targets.
- **Helps:** "what differs between targets?" at a glance.
- **Status:** Done; a test checks its cells against the newest real runs.

**2.2 Run diff**

- **What:** any two runs, even on different targets.
- **Status:** Done.

**2.3 Gap register**

- **What:** every gap on every target with status and reason; "copy as runbook table".
- **Status:** Done, plus gap kinds (19 Nov).

**2.4 Tests catalogue and test page**

- **Status:** Done.

**2.5 Conformance report**

- **What:** the vendor's deliverable, as one self-contained HTML file.
- **Status:** Done as the HTML export, labelled as a draft.

**2.6 Coverage report**

- **What:** the per-track coverage write-up in HTML and Markdown.
- **Status:** Not started.

**CP9, the Phase 2 exit:** the track owners compare the matrix and reports with what they produce today.

### 4.6 Phase 3: Vendor onboarding (not started)

**3.0 ABI spike**

- **What:** a plain `syncd` (the switch-state daemon) built against the project's pinned SAI headers (SAI v1.18.1),
  with `libsaivs.so` renamed to `libsai.so` under it.
- **Helps:** proves or disproves the whole idea of "bring your own `libsai.so`".
- **Why this way:** a vendor library must match the SAI headers it is used with. If swapping the library under a
  generic daemon doesn't work, Phase 3 must be designed differently. That is why it is tested first, and on a stand-in
  library we already have.

**3.1 A prebuilt base image**

- **What:** SAI-Challenger's base image plus that generic `syncd`, with no libSAI.
- **Helps:** a vendor image becomes one "copy `libsai.so`" layer, so building takes seconds, not a full source build.
- **Why this way:** today each libSAI is built from source inside its image, which a vendor with only a binary can't
  do.

**3.2 Static checks**

- **What:**
  - Is the file a 64-bit shared library?
  - Does it export the four SAI entry points?
  - Are all its dependencies present?
  - Does it have a SONAME (its library name)?
- **Helps:** catches a wrong file in seconds, before anything is built.

**3.3 Version probe**

- **What:** ask the library its SAI version in a short-lived container; warn if it differs from the pinned version.

**3.4 Generators**

- **What:** the target's folder, testbed file and profile with an empty gap list.

**3.5 The wizard**

- **What:** the five steps (upload, version, switch setup as forms, build, smoke test), plus Update libSAI and Remove
  target (reports are kept).

**3.6 First check**

- **What:** run SAI-Challenger's upstream baseline, then offer the full suite.

**Before any build (CP10):** a memory plan. The machine has about 3 GB free with three containers up, so a fourth may
not fit.

**Open:** how vendors map their ports to virtual interfaces for traffic tests is not defined in any document yet.

### 4.7 Phase 4: Developer tools (not started)

**4.1 Changes page**

- **What:** your branch against its base, the changed files and read-only diffs.

**4.2 Automatic checks**

- **What:**
  - profile JSON valid, with no duplicate keys;
  - `ruff`;
  - rule checks: no target names in test code, no non-strict or runtime xfail, no local `poc_ports` override, no port
    numbers written into tests, no `/opt/sai-poc` paths.
- **Helps:** catches rule breaks before review, not after.

**4.3 Check before PR**

- **What:**
  - the changed test files run twice on saivs;
  - traffic tests three times on saivpp (only if they changed);
  - the baseline on saivs;
  - then the PR text, and the git commands filled in for you to run by hand.
- **Why this way:** the UI never runs git for you (an earlier decision), so the commands are shown, not run.

**4.4 New test scaffold**

- **What:** a template using the PoC's helpers, then "open in your editor".
- **Why this way:** there is no code editor in the UI on purpose. An editor would make it easy to put target logic
  into tests.

**4.5 Test data forms**

- **What:** the data files, with the same validation the tests apply.

**4.6 Definition of done**

- **What:** the project's checklist, ticked from run history where possible.

### 4.8 Phase 5: Shared mode (not started)

**5.0 Decisions first, with the mentor**

- **What:**
  - which account the UI runs as (a service account needs a new mount and a container restart);
  - how people log in;
  - whether reserving the testbed also blocks terminal runs.

**5.1 Logins and two roles**

- **What:** admin and user.

**5.2 Admin container control**

- **What:** container Start, Stop and Restart for admins only, with a stated reason and a memory check.

**5.3 One queue across users**

- **What:** you cancel your own runs; an admin can cancel any, with a reason.

**5.4 Activity feed**

**5.5 Testbed reservations**

**CP13:** nothing is deployed on the team's machine without the mentor's sign-off.

### 4.9 The extra step: the Allure restyle (19 Nov 2026)

- **What:** the first look was plain. The owner asked for the look and the useful features of Allure Report. A mood
  board and a list of Allure's features were drawn up, the owner picked the features, and the rest was decided on
  "what looks and performs best".
- **Built:**
  - **The new look** (section 3.14).
  - **Pages:**
    - target cards;
    - the run page tree with split view and keyboard keys;
    - the test detail tabs;
    - the difference viewer;
    - the Causes, Gates and Charts views;
    - the heat map.
  - **Features:**
    - gap kinds;
    - flaky and transition marks;
    - Retry failures;
    - Rerun failed only;
    - the one-file HTML report;
    - the Markdown summary.
- **Helps:** a newcomer reads a run in seconds, and the history marks catch changes a single run can't show. For
  example, they flagged a test on saivs that had been an Expected gap for six runs and is now a plain Fail.
- **Why this way:** copying a proven layout was faster and better than inventing one (option (d) in 4.2 explains why
  Allure itself wasn't used).
- **Status:** Done; it is in this repository.

### 4.10 Where things stand

| Area | State |
|---|---|
| Reading every past run, plain words, hints, history marks, causes, gates, charts | Done |
| Matrix, run diff, gap register (with kinds), tests catalogue | Done |
| HTML conformance report and Markdown summary | Done |
| Starting runs (sheet, queue, live page, repeat, retry failures) | Built and unit-tested; **first real run (CP6) waits for the owner** |
| Cancel a started run | Not built: needs the 0.10 spike and sign-off |
| Phase 0 changes to SAI-Challenger | On hold until requested; the UI works without them |
| Editing profiles (adding and removing gaps) | Not started: after CP6, with the go-ahead |
| Coverage report, vendor onboarding, developer tools, shared mode | Not started |
| Checks | 62 server unit tests pass; `ruff` clean; the TypeScript check and the web build pass |

---

## 5. Questions a reviewer might ask

### The basics

**What problem does this solve, in one sentence?**
It turns "run a script, wait on an invisible lock, then read XML" into one page that runs the tests, shows who is
using each target, and says what every result means in plain words.

**Does the UI run tests itself?**
No. It starts `scripts/poc/run_poc.sh` with the same arguments a person would type, and "Show command" prints that
exact line. pytest runs inside the target's container exactly as it does from a terminal.

**Why not just use the terminal?**
You still can, and terminal runs appear in the UI automatically. The terminal shows expected gaps as PASSED, says
nothing about who holds a lock, and leaves comparison and history to separate scripts.

**What is the difference between Fail and Setup error?**
- **Fail:** the test ran and the target gave the wrong answer.
- **Setup error:** the test couldn't even start, for example because a fixture crashed. It says nothing about the
  target, so it is kept apart and coloured differently.

**What is an expected gap, and why "strict"?**
A known, recorded difference between a target and the SAI specification. It is listed in the target's profile with a
reason. "Strict" means that if the test starts passing, the run reports it, so a fixed gap can't hide in the profile
for ever.

**What should I do when I see "Gap now passes"?**
The target now does what the specification says, so the gap in its profile is out of date. Remove the gap; the test
then counts as a normal Pass.

**Why does the terminal say PASSED for an expected gap?**
A reporting hook in the PoC's conftest prints strict xfail as PASSED, on purpose, to keep the terminal output calm.
The XML file still records it as an expected failure, and that is what the UI reads.

**What is a target? Why three of them?**
A libSAI set up for testing, in its own container. saivs and saivs-thrift are the same virtual switch reached two
different ways. saivpp really forwards packets, so it is the only one that runs traffic tests.

**What are Level 1 and Level 2?**
- **Level 1:** set things up through SAI and check the answers.
- **Level 2:** also send packets and check where they arrive. Level 2 needs a target that forwards packets.

**Why are traffic tests skipped on saivs?**
saivs stores the switch configuration but moves no packets, so a traffic test there would prove nothing. The run sheet
says so in a sentence rather than offering a switch that wouldn't work.

**What is the MLD filter?**
saivpp sends its own IPv6 Multicast Listener Discovery packets now and then. Those stray packets can upset tests that
expect an exact set of packets. The PoC has a filter that ignores them. The run sheet offers auto, on or off, and only
when traffic tests will run.

**What is an upstream test?**
A test from SAI-Challenger's own suite rather than from `tests/poc`. Expected gaps never apply to them, and most
counts on the pages are about PoC tests.

### Results and numbers

**How do I know the UI's numbers are right?**
Three unit tests run against the real report folder:
- per-run counts equal `summarize.py`'s on every report;
- the matrix cells equal `summarize.py`'s view of the newest runs;
- the UI's copy of the gap rule gives the same answer as the conftest on every real profile entry.

**Why would the UI's Fail count differ from `summarize.py`'s "failed"?**
`summarize.py` folds setup and cleanup errors into "failed". The UI shows them separately. Add the UI's Fail and
error counts together and you get `summarize.py`'s number.

**What does the percentage in the donut mean?**
Pass divided by the tests that ran. Skipped tests are left out. Expected gaps and errors count as not passing,
because the target didn't do what the specification says.

**What does Flaky mean here?**
A test whose result keeps flipping on the same target, and which is failing now. The rule is Allure Report 3's, with
one change: runs that didn't select the test are left out (section 3.11).

**What are New, Fixed, Regressed and New error?**
- **New:** the first time this test ran on this target.
- **Fixed:** passes now; it failed, errored or was a gap before.
- **Regressed:** fails now; it didn't before.
- **New error:** errors now; it didn't before.

**What is a cause?**
A group of failures that share a reason, such as the same returned status, the same known signature, or "the packet
did not arrive". Ten failures with one cause are one problem, not ten.

**What is a gate? Does it change whether the run passes?**
A rule the run should meet, such as "no Fail" or "the full suite ran". Gates are shown in the UI only. They don't
change `run_poc.sh`'s exit code or anything in SAI-Challenger.

**Can the plain-words sentence be wrong?**
It is built from the message text. When a message names a status, that is sometimes the status the specification
wanted rather than the one returned. For that reason cause titles show just the status name. The raw message is
always one click away.

**What are gap kinds, and why aren't they in the profile?**
- **Limitation:** the target can't or won't do it.
- **Known bug:** with a link to it.
- **Temporary:** with a review date.

They are kept in the UI's own config folder, because adding a key to the profiles would change SAI-Challenger, and
that waits for the owner's request.

### Runs

**What happens if two people want the same target?**
`run_poc.sh` takes the target's lock, so runs never overlap. The UI shows who holds it and queues behind them. A
terminal run waits on the lock the usual way.

**What if I close the browser during a run?**
Nothing; the run is on the server. Open the UI again and it is still there.

**What if the UI server stops during a run?**
The run carries on: it has its own process session. When the server starts again, it finds the run by its process ID
and follows it to the end. Runs that were only queued are dropped and marked "Nothing was run".

**Can I cancel a run?**
Only before it starts (take it off the queue). Stopping a started run safely inside a shared container is an open
question (step 0.10), so the button is disabled and says why.

**What is the difference between Repeat and Retry failures?**
- **Repeat** runs the same selection 1 to 5 times, to look for instability.
- **Retry failures** reruns only what failed, up to 3 times, and marks a test that then passes as Retried.

**What does "Rerun › Failed only" do?**
It opens the run sheet with that run's failed tests (Fail, Setup error, Cleanup error) already picked. You still see
the plan and press Run yourself.

**How is the time estimate worked out?**
Each picked test's most recent duration on that target, the median for tests never seen there, plus 15 seconds for
start-up.

**What gets recorded with each UI run?**
- the exact command and the options;
- who started it;
- the commit and branch of the checkout;
- any uncommitted changes under `tests/poc` and `scripts/poc`.

The results themselves stay in the report file `run_poc.sh` writes.

**Where is the console output of a UI run?**
In `~/.local/state/sai-challenger-ui/jobs/<job id>.log`, and in the Run log tab. Terminal runs have no saved console
(the planned `.log` next to the report needs step 0.4).

### Safety and data

**Can the UI change test code or profiles?**
No. It has no code editor and no write access to profiles in this version. Gap editing (step 1.5) will write
profiles, and only after the owner agrees.

**Can it start or stop containers?**
No. It only reads `docker ps`. Container control is planned for admins in shared mode (Phase 5).

**What does it write, and where?**
See the table in section 3.3. In SAI-Challenger, only what `run_poc.sh` itself writes when the UI starts a run.

**Can someone on another machine start a run?**
Not by default: the server listens on `127.0.0.1`. Actions also need a special header, a localhost Host and Origin,
and a JSON body, so a web page on another site can't trigger them. Anyone logged in to the same machine can reach it;
logins come with shared mode.

**Could a crafted request run a shell command?**
No. Requests carry only choices, which are checked against known targets, a fixed list of markers and the catalogue.
`run_poc.sh` is started with a list of arguments, never through a shell.

**Does it need the internet?**
No. Fonts are bundled and the web app is built to static files. Node is needed only to build the web app, not to run
it.

**Is the HTML report ready to send to a vendor?**
It is a draft. Its footer says so, and anything that leaves the team is reviewed by its owner first.

### Design choices

**Why a separate repository?**
The owner decided to keep UI code out of the shared test repository until the team agrees. The UI reads the checkout
through a path setting (`SAI_CHALLENGER_UI_SC_ROOT`).

**Why does the UI run on the host and not in a container?**
`run_poc.sh`, `exec.sh` and the mounts all depend on host paths and need Docker access.

**Why Python and FastAPI for the server?**
The PoC is Python, so the server can reuse its rules directly. FastAPI handles background subprocesses well and is
small.

**Why React for the web app?**
The pages are dense and interactive: trees, filters, split views, live updates. TanStack Query handles the polling and
caching; Radix gives accessible menus, tabs and tooltips without a stock look.

**Why poll every second instead of using WebSockets?**
Polling works through VS Code's port forwarding with no extra setup, and runs last minutes, so a one-second refresh is
plenty. Pages poll only while something is active.

**Why read the console when an event file would be exact?**
The event file needs a conftest change (step 0.5), which is on hold. The console is good enough to show progress, and
the XML file corrects anything at the end.

**Why build the catalogue by reading the files instead of asking pytest?**
Asking pytest means taking the lock and running in a container. Reading the files needs neither, and past reports
fill in the parameter values the files don't contain.

**Why copy Allure's look rather than use Allure?**
See option (d) in section 4.2: using Allure would change the test containers, might blur Expected gap and Gap now
passes, and wouldn't give run control or gap editing.

**Why so many colours if colour is "only for results"?**
Each colour is one result word and nothing else. Every result also has its own shape, so colour is never the only
signal.

### Status and limits

**What exactly has been tested?**
62 unit tests on the server, covering:
- report parsing and parity with `summarize.py`;
- the gap rule;
- the catalogue;
- planning and refusal of unknown input;
- the queue, including a full run against a stand-in `run_poc.sh`, waiting on a held lock, the request guard, the
  one-owner rule and restart behaviour;
- the history marks, causes, gates, gap kinds, exports and Retry failures.

Every page was also checked in a headless browser against the real reports, in both themes.

**What hasn't been tested?**
A real run started from the UI. That is checkpoint CP6, and it waits for the owner.

**What is the CP6 check, exactly?**
Start one saivs run from the UI, run the same command from a terminal, and compare the two XML files' results.

**What is known to be incomplete?**
- No Cancel.
- No packets panel or export zip.
- No profile editing.
- The difference viewer appears only when the message carries both values.
- The old static look preview (`python -m sai_challenger_ui.preview`) still uses the first look.
- The web app's bundle is 536 kB; it could be split later.

**What is not decided, or not known from any document?**
- Whether a vendor `libsai.so` works under a generic `syncd` (spike 3.0).
- How vendors map their ports for traffic tests.
- The Cancel method.
- Which account the UI runs as in shared mode, and how people log in.
- The app's final name.

---

## 6. Reference

### 6.1 Glossary

| Term | Meaning |
|---|---|
| **ASIC** | The switch chip that moves packets in hardware |
| **SAI** | Switch Abstraction Interface: a common programming interface for switch chips |
| **libSAI** (`libsai.so`) | A chip vendor's implementation of SAI |
| **syncd** | The daemon that applies switch configuration to the chip through libSAI |
| **sairedis / saithrift** | Two ways of reaching a libSAI: through a Redis-based message layer, or a remote-call layer |
| **saivs** | SAI's virtual switch: a software libSAI that stores objects but forwards no packets |
| **VPP / saivpp** | FD.io VPP, a software packet forwarder; saivpp is a libSAI that programs it |
| **SAI-Challenger** | The open-source SAI test framework the PoC is built on |
| **PoC** | The proof-of-concept test suite in `tests/poc` and its scripts |
| **Target** | One libSAI set up for testing, in its own container, with its own profile |
| **Profile** | `tests/poc/targets/<target>.json`: testbed, ports, lock, expected gaps |
| **Expected gap** | A recorded difference from the SAI specification, run as strict xfail |
| **Scope gap** | Something not tested on a target at all, listed for the record |
| **Strict xfail / XPASS(strict)** | pytest's "expected to fail" mark, where an unexpected pass counts as a failure |
| **Track** | A subject area of tests: A (L2 and VLANs), B (L3 routing), C (ACL and counters) |
| **Level 1 / Level 2** | Control-plane tests / traffic tests |
| **Step scenario** | Numbered tests that build on each other; later steps need earlier ones |
| **Upstream test** | A test from SAI-Challenger itself, not from `tests/poc` |
| **PTF** | The packet test framework used to send and check packets |
| **MLD** | IPv6 Multicast Listener Discovery; saivpp's own MLD packets are filtered out in traffic tests |
| **pytest marker** | A label on a test (`l2`, `traffic`, `negative`) used to select and group tests |
| **Node ID** | pytest's full name of a test: `file.py::Class::test_name[param]` |
| **JUnit XML** | The machine-readable report file pytest writes; the UI's source of truth |
| **flock / lock** | A file lock per target, so only one run uses a target at a time |
| **`run_poc.sh`** | The PoC's run script: takes the lock, runs pytest in the container, writes the reports |
| **`exec.sh`** | SAI-Challenger's script for running a command inside a target's container |
| **`summarize.py`** | The PoC's script that compares targets from the report files |
| **Run** | One report file pair (`<target>-<stamp>.xml/.html`) |
| **Job** | A run as the UI knows it: queued, running or done, with its own record and console log |
| **Run set** | The runs of one request with Repeat above 1 |
| **Catalogue** | The UI's list of every test, built by reading the test files |
| **Hint** | Advice attached to a known failure signature (`hints.toml`) |
| **Cause** | A group of failures that share a reason |
| **Gate** | A rule a run should meet, checked by the UI only |
| **Transition** | New, Fixed, Regressed or New error, against earlier runs |
| **Flaky** | A test whose result keeps flipping and is failing now |
| **Gap kind** | Limitation, Known bug or Temporary |
| **Checkpoint (CP)** | A point where work stops for the owner's review |

### 6.2 Code map

```
server/
  pyproject.toml              package sai-challenger-ui; the core needs no packages, the server needs fastapi+uvicorn
  sai_challenger_ui/
    cli.py                    the sai-challenger-ui command (--host, --port)
    settings.py               paths, overridable by environment variables
    hints.toml                failure signature → hint, with a short title per cause
    target_facts.toml         "forwards packets" per target, until profiles carry it
    core/                     standard library only
      vocab.py                the six result words, glyphs, order, headline
      junit.py                one JUnit XML file → results (errors kept apart)
      reports.py              the reports folder → runs; "since the previous run"
      profiles.py             profiles, the gap rule, gap status, unrecorded gaps
      catalog.py              the test catalogue, read with ast
      testbed.py              container state, lock holder, memory (read-only)
      explain.py              plain-words sentence, expected/actual, hints
      runview.py              run page groups, step scenarios, test detail
      compare.py              matrix, run diff, gap register, test history
      history.py              transitions, flaky, age, trends, stability
      causes.py               failures grouped by cause
      gates.py                conformance gate rules
      gapnotes.py             gap kinds in the UI's config folder
      selection.py            run sheet choices → run_poc.sh arguments
      console.py              live progress from pytest -v console lines
      jobs.py                 the queue per lock, starting and following run_poc.sh
      exports.py              one-file HTML report, Markdown summary
    api/
      app.py                  every /api endpoint, the request guard, static serving
      state.py                cached profiles, runs, catalogue, docker state
      serialize.py            core objects → JSON for the web app
    preview/                  the old static look preview (checkpoint CP5); out of date
  tests/                      62 unit tests (host only; no target, container or lock)
web/
  src/main.tsx                routes and the top bar
  src/api.ts                  types, data hooks and polling intervals
  src/RunSheet.tsx            the run sheet
  src/Activity.tsx            the top bar's activity chip and finished messages
  src/pages/                  Targets, Runs, Run, Job (live run), Compare, Tests
  src/components/             TestTree, TestDetail, DiffModal, GapNote
  src/charts.tsx              the SVG charts
  src/ui.tsx, icons.tsx       shared pieces (donut, pills, strip, marks) and icons
  src/styles/                 tokens.css (colours, sizes), look.css, app.css
  src/fonts/                  PT Root UI and JetBrains Mono, with their licence
  scripts/shot.mjs            screenshots for checking the look on a headless machine
```

### 6.3 Running, testing and configuring

Set-up is in the [README](../README.md). On a machine without `pip` or a working `venv`, `uv` can create the
environment instead:

```bash
cd server
uv venv --python /usr/bin/python3.12 .venv
uv pip install --python .venv/bin/python -e '.[server,dev]'
```

Run:

```bash
cd web && npm run build                       # once, and after every change to web/
cd ../server && .venv/bin/sai-challenger-ui --port 8770
# open http://127.0.0.1:8770
```

Test:

```bash
cd server && .venv/bin/pytest -q              # the UI's own tests; they never touch a target
```

Environment variables:

| Variable | Default | What it sets |
|---|---|---|
| `SAI_CHALLENGER_UI_SC_ROOT` | `~/SAI-Challenger` | The SAI-Challenger checkout |
| `SAI_CHALLENGER_UI_LOCK_DIR` | `/opt/sai-poc/locks` | Where `run_poc.sh` keeps its lock files |
| `SAI_CHALLENGER_UI_CONFIG` | `~/.config/sai-challenger-ui` | `gap_notes.json`, `gates.toml`, `target_facts.toml` |
| `SAI_CHALLENGER_UI_STATE` | `~/.local/state/sai-challenger-ui` | UI run records and console logs |
| `SAI_CHALLENGER_UI_MODE` | `local` | Only `local` may start runs today |

How often the web app refreshes:

| Data | Interval |
|---|---|
| The live run page | 1 s while the run is queued or running |
| The activity chip | 1.5 s while any UI run is active, otherwise 5 s |
| The targets page | 5 s |
| Free memory | 10 s |
| The reports folder (server side) | checked at most once a second |
| `docker ps` (server side) | at most every 3 s |

To add a hint, add a `[[hint]]` entry to `server/sai_challenger_ui/hints.toml` with a pattern, the results it applies
to, the text and a short title. The first matching entry wins, so put specific signatures first. To set your own gate
rules, write `~/.config/sai-challenger-ui/gates.toml`; the format is at the top of `core/gates.py`.
