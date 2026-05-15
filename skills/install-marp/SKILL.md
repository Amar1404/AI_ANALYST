---
name: install-marp
description: >
  Check if npm is available and install Marp CLI globally for presentation
  generation. Triggered when users say "install marp", "set up presentations",
  "enable slide generation", or invoke `/install-marp`.
---

# Skill: Install Marp

## Purpose
Check if npm is available and install the Marp CLI (@marp-team/marp-cli) globally
so that presentations can be generated from markdown files.

## When to Use
- User says "install marp" or "set up presentations"
- When the user wants to generate slides from markdown using Marp
- First time generating presentation output (check for Marp availability)

## Invocation
`/install-marp` — install Marp CLI globally
`/install-marp --check` — verify Marp is already installed
`/install-marp --version` — check installed version and update if needed

## Instructions

### Step 1: Check npm Availability

```bash
which npm
npm --version
```

If npm is not found:
```
npm is not available on this system. To use Marp, you need Node.js and npm installed.
Visit https://nodejs.org/ to download and install Node.js (which includes npm).
After installation, run `/install-marp` again.
```

### Step 2: Check for Existing Marp Installation

```bash
npm list -g @marp-team/marp-cli 2>/dev/null || echo "not installed"
```

If already installed:
```
Marp CLI is already installed globally.
Version: {version}
Ready to generate presentations!
```

### Step 3: Install Marp

```bash
npm install -g @marp-team/marp-cli
```

Track progress and report:

```
Installing Marp CLI...
[===>       ] 45%

Installation complete!
Version: {version}
Location: {global npm path}

You can now generate presentations from markdown files.
Usage: marp {input.md} -o {output.pdf}
```

### Step 4: Verify Installation

```bash
marp --version
```

Confirm output shows version number.

### Step 5: Report Status

```
Marp installation verified!

You can now:
- Generate HTML slides: marp input.md -o output.html
- Generate PDF: marp input.md -o output.pdf
- Generate PPTX: marp input.md -o output.pptx
- Use Marp in the analysis pipeline to create presentation decks

Next: Use the Deck Creator agent to generate presentation markdown,
then convert with Marp.
```

## Edge Cases
- **Permission denied:** "npm requires elevated permissions. Try `sudo npm install -g @marp-team/marp-cli` or contact your system administrator."
- **npm out of date:** Suggest updating: `npm install -g npm`
- **Version conflicts:** Remove old version first: `npm uninstall -g @marp-team/marp-cli` then reinstall
- **Offline mode:** "Marp installation requires internet connection to download. Please check your connection and try again."

## Anti-Patterns
1. **Never run as root unless necessary** — use `npm config set prefix` to set user-scoped npm directory
2. **Never install multiple times** — check first with `--check` flag
3. **Never assume Marp is always needed** — only install on user request
4. **Never skip the verification step** — confirm version is as expected after install

## Usage After Installation

Once installed, Marp can be called by presentation generation agents:

```bash
# HTML presentation
marp presentation.md -o presentation.html

# PDF slides
marp presentation.md -o presentation.pdf --pdf

# PPTX (requires additional theme setup)
marp presentation.md -o presentation.pptx
```

Marp markdown syntax:
- `---` separates slides
- `# Title` for slide heading
- `![bg](image.png)` for background image
- `<!-- _class: lead -->` for special slide styles
