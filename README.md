<h1 align="center"><img src="assets/icon.jpg" alt="MacAgentBench icon" width="64" style="vertical-align: middle;">&nbsp; MacAgentBench: Benchmark agents where they actually work — on macOS.</h1>

<p align="center">
  <strong>A macOS benchmark for evaluating AI agents on real desktop tasks.<br>
Reproducible tasks, rule-based evaluation, and native app coverage across everyday work scenarios.<br>
<a href="#quick-start">Fully configured OpenClaw macOS image for Linux and Windows</a></strong><br>
</p>

<p align="center">
  <a href="https://jetastra.github.io/MacAgentBench/"><img src="https://img.shields.io/badge/Leaderboard-Live-red?style=for-the-badge" alt="Leaderboard"></a>
  <a href="#quick-start"><img src="https://img.shields.io/badge/Quick_Start-5_min-blue?style=for-the-badge" alt="Quick Start"></a>
  <a href="#benchmark-feature"><img src="https://img.shields.io/badge/Categories-18-green?style=for-the-badge" alt="Categories"></a>
  <a href="https://github.com/JetAstra/MacAgentBench/tree/main/task"><img src="https://img.shields.io/badge/Tasks-110-brightgreen?style=for-the-badge" alt="Tasks"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge" alt="License"></a>
</p>


<p align="center">
  <img src="assets/intro.png" alt="intro" width="800">
</p>

---
## 🔎TL;DR

1. We provide a fully configured macOS-based OpenClaw environment that runs out-of-the-box on both Linux and Windows via Docker. In addition, we address the complex permission issues in macOS, ensuring that OpenClaw can execute tasks without failing due to permission restrictions. Everyone is welcome to try it out and contribute! 👏
2. We introduce a benchmark designed to evaluate OpenClaw in real-world usage scenarios. 
It covers both the default tasks supported by OpenClaw and tasks commonly encountered in real working environments.

3. Our evaluation relies on manually designed rule-based evaluators, avoiding the uncertainty introduced by using LLMs as judges.
Each task is executed in an independent container, ensuring that tasks do not interfere with each other during evaluation.

<a id="quick-start"></a>

## 🚀Quick Start

Want to try the image first? Start with Part 1. Want to run benchmark evaluation? Jump to Part 2.

### 1. Try OpenClaw in macOS on Linux or Windows

1. Download the required image files from Hugging Face (~40GB):

```bash
pip install huggingface_hub

huggingface-cli download JetLM/OpenClaw-macOS --local-dir .
```

2. Start the macOS Docker container:

```bash
bash launcher/docker/simple_start.sh
```

3. Connect to macOS:

```bash
vncviewer localhost:5901
```

Next, open OpenClaw. You should see the OpenClaw icon in the top menu bar, which means you are ready to start using OpenClaw on macOS.

<p align="center">
  <img src="assets/macos.png" alt="OpenClaw running inside macOS" width="900">
</p>

### 2. Run the evaluation benchmark

1. Download the required image files from Hugging Face (~50GB):

```bash
pip install huggingface_hub

huggingface-cli download JetLM/OpenClaw-macOS --local-dir .
```

2. Fill in your API key and base URL in [`openclaw.json`](/home/fuyikun/Documents/MacAgentBench/openclaw.json).

3. Update the required local paths in [`eval.sh`](/home/fuyikun/Documents/MacAgentBench/eval.sh), especially the image paths and your local `WORK_DIR`.

4. Start the evaluation:

```bash
bash eval.sh
```

<a id="benchmark-feature"></a>

## 📋Benchmark feature

1. Compared to existing benchmarks for evaluating OpenClaw (e.g., PinchBench and Terminal Bench), our benchmark focuses primarily on real-world user scenarios.
All tasks are executed on macOS rather than Linux, bridging the gap between evaluation environments and actual usage scenarios. This provides a more realistic assessment of OpenClaw’s capabilities in everyday workflows.

2. Our benchmark supports testing all skills provided by OpenClaw by default, ensuring that even newly deployed lobsters 🦞 can be evaluated fairly and comprehensively.

3. The benchmark includes a wide range of macOS-specific scenarios and capabilities, such as productivity workflows using Apple Numbers, Apple Pages, and Apple Keynote, as well as native macOS applications like Notes, Reminders, and other GUI-dependent tasks.
This allows us to evaluate OpenClaw’s capabilities from multiple perspectives across realistic desktop workflows.

<!-- 4. The tasks included in the benchmark are collected from frequent real-world usage scenarios shared by users of OpenClaw across the internet. -->


Our benchmark currently covers **110** tasks across **18** macOS app and tool categories, reflecting real-world OpenClaw usage scenarios. Each task is designed to test specific capabilities, from productivity apps to terminal utilities.

| App             | Task Focus                  | Example Instruction                                                                                                                                                                                                        | # of Tasks |
| :-------------- | :-------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--------- |
| Apple Notes     | Note management             | `In Apple Notes, edit the note titled "Project Ideas" and append the line "Reviewed on Tuesday.".`                                                                                                                         | 8          |
| BlogWatcher     | Subscribe to blogs          | `In blogwatcher, scan all tracked blogs for updates.`                                                                                                                                                                       | 7          |
| 🦞 ClawHub      | Control OpenClaw SKILLs     | `From ClawHub, install "incident-triage-playbook" at version "1.0.0" into "$HOME/Desktop/clawhub_skills_1_1".`                                                                                                             | 2          |
| GifGrep         | Search & share GIFs         | `Find the first Tenor GIF result for "cat typing on keyboard", then download that GIF and save it as "$HOME/Desktop/gifgrep_download_2_1.gif".`                                                                             | 4          |
| GitHub          | Store & share code          | `Find the latest open issue in "openclaw/openclaw" with label "bug", and save it as "#<number> \| <labels> \| <title>" to "$HOME/Desktop/gh_open_issues_2_1.txt".`                                                       | 5          |
| Himalaya        | Send & receive emails       | `Check the latest OTP email in Inbox (search across all pages) and save only one line to "$HOME/Desktop/mail_otp_1_1.txt" as "otp_code: <6-digit-code>". If no OTP email exists, write "otp_code: none".`                  | 8          |
| Obsidian        | Manage Markdown files       | `In Obsidian, create a new note called "Inbox/Vendor Call Notes.md" and set its content exactly to the provided meeting notes.`                                                                                             | 8          |
| Peekaboo        | Launch and inspect apps     | `Capture a PNG screenshot of the TextEdit window and save it to "$HOME/Desktop/peekaboo_front_window_1.png".`                                                                                                               | 8          |
| Reminders       | Task reminders              | `In the Reminders app, create a new reminder titled "Dentist follow-up" due "2026-04-15 09:30".`                                                                                                                          | 10         |
| Sherpa-ONNX-TTS | Text to speech              | `In Terminal, create a spoken reminder that says "Reminder: submit the travel reimbursement form today.", and save it as a WAV file to "$HOME/Desktop/sherpa_tts_2_1.wav".`                                                | 2          |
| SongSee         | Audio to spectrogram        | `In Terminal, use songsee to generate a multi-panel visualization for "$HOME/Desktop/Ode to Joy.mp3" with spectrogram, mel, chroma, and mfcc, then save it to "$HOME/Desktop/songsee_panel_1.png".`                      | 9          |
| tmux            | Terminal session management | `In Terminal, send "status" to the tmux session "tmux-status-send-c1", then save the reply to "$HOME/Desktop/tmux_result_4_1.json".`                                                                                       | 6          |
| Video Frames    | Extract frames              | `In Terminal, extract a frame at 00:00:01 from "$HOME/Desktop/benchmark_source.mp4", resize it to 640x720, and save it as "$HOME/Desktop/vf_thumb_1.png".`                                                                | 3          |
| Weather         | Check weather               | `Can you check tomorrow's weather in "San Francisco" and tell me whether it will be rainy? Save only one yes/no line to "$HOME/Desktop/weather_tomorrow_rain_2_1.txt".`                                                   | 4          |
| Whisper         | Speech to text              | `In Terminal, use Whisper's tiny model to make an SRT subtitle file for "$HOME/Documents/whisper_audio_en_2.ogg" and save it to "$HOME/Desktop/whisper_subtitles_2_1.srt".`                                               | 4          |
| Numbers         | Create & manage tables      | `In the Numbers app, create a new blank document, insert a table into the first sheet if needed, then enter the value "test" into cell A1.`                                                                                | 5          |
| Pages           | Writing & reading           | `In the Pages app, create a new document using the "Blank Black" template and write: Passwd: 111111.`                                                                                                                      | 8          |
| Keynote         | Build slides                | `In the Keynote app, create a new document, export it to PowerPoint, and save it to the Documents folder.`                                                                                                                 | 9          |

## 🗺️RoadMap
#### What we have done
- [x]  Build a fully configured OpenClaw environment

- [x] Add all task supported by default OpenClaw SKILLs

- [x] Add daily work macOS tasks

- [x] Build a leaderboard website

- [x] Test on a few advanced models
  - [x] Claude 4.6 opus
  - [x] GPT5.4
  - [x] Minimax m2.5
  - [x] KIMI 2.5 

#### Upcoming Plans(coming soon...)
- [ ] Add more tasks (calender, clock, finder...)

- [ ] Test on more models
  - [ ] Qwen 3.5
  - [ ] Deepseek 3.2
  - [ ] ...

## 🙌 Contribution Guide
We warmly welcome contributions to improve the OpenClaw Benchmark for macOS! Here’s how you can help:

1️⃣ Add Support for New Models
- Integrate support for new language or agent models.

- Test existing tasks on new models and report results.

- Ensure compatibility with our Docker-based OpenClaw environment.

2️⃣ Add New Tasks
- Submit new macOS tasks that reflect real-world user scenarios.

- Provide clear instructions, expected outputs, and, if possible, configuration screenshots or screen recordings.

- Include tasks across different apps (productivity, terminal utilities, GUI-based apps) to enrich the benchmark coverage.

3️⃣ Verification & Automation
- Write verification scripts for tasks to ensure consistency and correctness.

- Automate detection of inactive platforms or failed task execution.

4️⃣ Translations & Localization
- Translate task instructions or documentation into English, Japanese, Korean, or other languages.

- Help make the benchmark accessible to a broader community.

#### How to Contribute
- Fork the repository.

- Make your changes in a separate branch.

- Submit a Pull Request with a clear description of your contribution.

- If unsure, open an Issue first to discuss your idea—we respond quickly!

💡 Tip: When adding tasks, try to follow the existing format in tasks/ and include example instructions similar to the ones in our benchmark table.

## ❤ Acknowledgments
We would like to thank the following projects and communities for their invaluable contributions, which helped make this benchmark possible:

OpenClaw - https://github.com/openclaw/openclaw

OpenGVLab – https://github.com/OpenGVLab

Docker-OSX – https://github.com/sickcodes/Docker-OSX

## 📬 Contact
If you have questions or would like to collaborate, please contact us at:

- [Yikun Fu](https://github.com/JiaranI), Shanghai AI Laboratory
  📧 fuyikun123456@163.com

- [Bowen Fu](https://github.com/HappyBug7), XJTU
  📧 HappyBug@stu.xjtu.edu.cn

- [zhenyu wu](https://github.com/numbmelon)
  📧 zywu01@sjtu.edu.cn

- [kaiyan zhang](https://github.com/iseesaw)
  📧 zhang-ky22@mails.tsinghua.edu.cn

  
- [Biqing Qi](https://github.com/Biqing-Qi), Shanghai AI Laboratory
  📧 qibiqing@pjlab.org.cn
