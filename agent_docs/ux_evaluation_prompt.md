# UX Evaluation Prompt for Indico Crosstab

> Copy this prompt into Claude in Chrome. Then navigate to https://crosstab.indicolabs.io and share your screen or take screenshots at each step.

---

## Prompt

You are a UX researcher evaluating **Indico Crosstab** — a web tool that lets market researchers upload SPSS (.sav) files and generate professional Excel crosstabs with significance testing.

**Target user**: A market research analyst (30-50 years old) who currently uses PSPP, WinCross, or SPSS to create crosstabs manually. They are not developers — they don't know what an API is. They want to upload a file, configure their tables, and download an Excel.

**URL**: https://crosstab.indicolabs.io

### Your task

Navigate the full user journey and evaluate every screen, interaction, and decision point. Be brutally honest — this tool needs to be intuitive enough that someone can use it without documentation.

### Step-by-step evaluation

#### 1. First Impression (5 seconds)
- What do you understand this tool does?
- Is the value proposition clear?
- Does it look trustworthy/professional?
- What's missing from the landing view?

#### 2. File Upload
- Upload a .sav file (use any test file or note what happens with no file)
- Is the drag & drop obvious?
- Is the .docx upload purpose clear? Would a non-technical user understand "Reporting Ticket"?
- After upload: is the metadata display useful? Is it overwhelming?

#### 3. Auto-Analyze (One-click button)
- Is the "One-click analysis" button visible and compelling?
- Is the description clear enough? Would you trust it?
- Click it — is the loading state informative?
- When results appear: is the success message clear? Can you easily download?

#### 4. Manual Configuration
- **Banners section**: Are the "Recommended banners" and "Other variables" sections clear?
  - Can you tell what a "banner" means without prior knowledge?
  - Are the chips easy to read? Is label vs variable name clear?
  - Can you easily add/remove banners?

- **Stubs section**: Is "All variables" vs "Select specific" clear?
  - Would a researcher understand "stubs"?

- **MRS section**:
  - Is "Multiple Response Sets" explained well enough?
  - Are the auto-detected groups obvious? Can you tell they were auto-populated?
  - Is the manual add flow intuitive?
  - Can you easily remove an auto-detected group?

- **Grid/Battery section**:
  - Same questions as MRS
  - Is the difference between MRS and Grid clear?

- **Options section**:
  - Significance level: obvious?
  - Weight variable: would a non-weighted study user be confused?
  - Report title: useful or unnecessary?
  - T2B/B2B checkbox: is the label clear?
  - Means toggle: clear?
  - Output mode (one sheet vs multi sheet): is the description helpful?

- **Custom Groups section**:
  - Is the purpose of "Custom Groups" clear?
  - Is the condition builder intuitive?
  - Is AND logic explained?

#### 5. Generate Excel
- Is the summary bar before the button helpful?
- Click Generate — is the loading state informative?
- Success: is the result message clear?
- Can you easily find the download button?
- Is the file name meaningful?

#### 6. API Reference (expandable section at bottom)
- Is it useful for a non-developer?
- Is it useful for a developer?
- Are the code examples correct and clear?

#### 7. Overall UX Issues

For each issue found, rate:
- **Severity**: Critical / Major / Minor / Enhancement
- **Category**: Clarity / Navigation / Visual / Functionality / Accessibility
- **Recommendation**: Specific fix

#### 8. Missing Features (from a researcher's perspective)
What would a market researcher expect that isn't here?
- Data preview/table view?
- Variable search/filter?
- Export to PowerPoint?
- Save/load configurations?
- User accounts?
- Pricing page?
- Help/tutorial?

#### 9. Competitive Analysis
Compare the UX to:
- PSPP (free, desktop)
- SPSS Statistics (paid, desktop)
- Web tabulation platforms (paid)
- Q Research Software (web, paid)

What does Indico Crosstab do better? What does it do worse?

#### 10. Final Score

Rate each dimension 1-10:
| Dimension | Score | Notes |
|-----------|-------|-------|
| First impression / clarity | | |
| Ease of use (non-technical user) | | |
| Ease of use (technical user) | | |
| Visual design / professionalism | | |
| Feature completeness | | |
| Error handling / feedback | | |
| Mobile responsiveness | | |
| Accessibility | | |
| **Overall UX Score** | | |

### Deliverable

Provide:
1. **Executive Summary** (3-5 bullet points)
2. **Detailed Issue List** (table: severity, category, description, recommendation)
3. **Top 5 Quick Wins** (changes that would have the biggest impact with the least effort)
4. **Top 3 Structural Changes** (bigger changes for the next sprint)
5. **Screenshots or descriptions** of each problem area
