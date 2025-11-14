QSOLAI
Quantum-Sourced Optimization Logic — AI Kernel

A QSOL-IMC Research Framework by Trent Slade










Overview

QSOLAI is the core AI kernel of the QSOL-IMC ecosystem — a modular, deterministic, minimal-dependency framework for exploring:

Quantum Error Correction (QEC)

Unified Field Theory (UFT) prototypes

Qutrit encoders

Spectral algebraics & audio DSP

Sonification templates

Pattern-logic, memetics, and information vortices

This project is designed for researchers, tinkerers, artists, theorists, and scientists who want fast iteration, reproducible runs, and clean architecture without heavy frameworks or bloated dependencies.

Small is beautiful. Fast is holy. Deterministic by default.

Features
Core Architecture

Modular structure: encoder/, runner/, sonifier/, analysis/.

Single-seed deterministic execution.

Lightweight dependency footprint.

CLI interface for experiments and sonification runs.

Clean JSON/YAML configuration workflow.

Quantum + DSP + Memetics

Qutrit encoder with upcoming unit tests.

Quantum-inspired logic mapping (QSOL signatures).

Sonification module for audio-based data exploration.

Research templates for UFT/TFT integration.

Memetic logic tools (pattern detection, embedding prep).

Reproducibility

Each run generates:

metadata.json

Seed logs

Audio/visual outputs (if enabled)

Experiment snapshots

Repository Structure
QSOLAI/
├── encoder/          # Qutrit encoder, transformations, unit tests (in progress)
├── runner/           # Deterministic run engine, CLI entrypoint
├── sonifier/         # Audio DSP tools, templates, spectral algebraics
├── analysis/         # Logs, metadata exporters, summaries
├── config/           # experiment.yml / config.yml templates
├── assets/           # diagrams, architecture images
├── tests/            # pytest unit tests
├── README.md         # You are here
└── requirements.txt  # Minimal Python deps

Installation
Prerequisites

Python 3.11+

ffmpeg (required for sonification output)

Git

Clone & Setup
git clone https://github.com/QSOLKCB/QSOLAI.git
cd QSOLAI

python -m venv venv
source venv/bin/activate  # macOS/Linux
# or: venv\Scripts\activate  # Windows

pip install --upgrade pip
pip install -r requirements.txt

Quick Start
1. Configure an Experiment

Edit config/config.yml or use the provided template:

seed: 42
mode: run
sonification: true
output_dir: results/
template: default
qutrit_encoder: true

2. Run the System
python runner/runner.py --config config/config.yml

3. View Outputs

After running, you’ll find:

results/sonification.wav — audio output

results/log.txt — full deterministic log

results/metadata.json — seed, versioning, module info

results/data.npz — encoded arrays, model outputs (if enabled)

Deterministic Execution

QSOLAI uses explicit seeds at all stages:

seed: 42


This ensures:

identical output across machines

reproducibility for scientific workflows

deterministic sonification

repeatable QEC/QSOL logic routines

All modules must respect this seed constraint.
(Contributors: don’t introduce nondeterminism without a clear switch.)

Modules
Encoder

Qutrit encoding

Tensor transformations

Basis cycling

(Upcoming) Full unit tests for deterministic mapping

Runner

Main orchestrator

Loads config

Applies global seed

Manages module order

Handles logging + reproducibility

Sonifier

Audio-DSP pipeline

Spectral algebraics tools

Standardized sonification templates

Generates .wav or .flac output

Optional spectral visualizations

Analysis

Metadata export

Result summaries

Run comparisons

Seed verification utilities

Dependencies

Minimal, clean Python stack:

numpy

scipy

librosa (if audio enabled)

soundfile

pyyaml

pytest (dev)

System requirement:

ffmpeg

Roadmap (v1 → v2)

 Complete qutrit encoder test suite

 Add deterministic “v1 runner” finalization

 Standardize sonification templates

 Integrate UFT/TFT experimental modules

 Metadata indexing for multi-run comparison

 CI pipeline with reproducibility checks

 Optional Rust backend for ultra-minimal builds

Contributing

PRs are welcome — but respect the following:

No bloat.
Every dependency must justify itself.

Determinism first.
All randomness must use the global seed.

Modular code.
No dumping everything into runner.py.

Readable logic > clever magic.
Future you should understand current you.

License

MIT License.
See LICENSE for full text.

Citation

When referencing this repository in academic or research work:

Slade, T. (2025). QSOLAI: Quantum-Sourced Optimization Logic AI Kernel.  
QSOL-IMC Research Group. GitHub: https://github.com/QSOLKCB/QSOLAI  
DOI: (Zenodo DOI pending)

Acknowledgements

This project is part of the growing QSOL-IMC universe, including:

QEC — Quantum Error Correction Framework

UFT — Unified Field Theory

Spectral Algebraics

Dark-Country Industrial Sonification Series

QSOL Synth, LOSTSOUND, QNToy

AI-assisted development supported through iterative research dialogue with ChatGPT.
