# PaperLens — Research Study Studio

PaperLens is a research-paper learning assistant. Upload a text-based PDF and turn it into an evidence-linked study guide, paper Q&A, research critique, interactive viva practice, and a PowerPoint presentation plan.

## What makes this version distinctive

- **Evidence-linked Q&A:** retrieves relevant passages from the uploaded paper and cites the source page numbers.
- **Interactive viva examiner:** asks one paper-specific question at a time, evaluates the student's answer, and provides constructive feedback.
- **Research critique:** separates limitations explicitly stated by the authors from cautious reader observations.
- **Audience-aware presentation builder:** creates a slide plan for classmates, faculty, or a technical audience and exports it to `.pptx`.
- **Adaptive explanations:** beginner, undergraduate, and advanced explanation levels.

## Technology stack

- Python and Streamlit — interactive web interface
- Gemini 3.8 Flash — language model
- Gemini Embedding 2 — text embeddings
- LangChain PromptTemplate + LCEL — prompt construction and model pipeline
- ChromaDB — vector database
- Retrieval-augmented generation (RAG) — grounds answers in the uploaded paper
- Intent routing — separates overview, Q&A, critique, viva, and presentation tasks
- PowerPoint (`python-pptx`) — downloadable presentation

## Architecture

1. User uploads a PDF.
2. `pypdf` extracts page text and preserves page metadata.
3. `RecursiveCharacterTextSplitter` creates overlapping chunks.
4. Gemini Embedding 2 converts chunks into vectors.
5. ChromaDB stores the vectors and retrieves relevant passages.
6. The task router selects the requested workflow.
7. A LangChain prompt template and LCEL chain send the question plus retrieved evidence to Gemini.
8. The result is shown in Streamlit; the presentation workflow can export a `.pptx`.

## Installation

Python 3.10–3.12 is recommended.

```bash
python -m venv venv
```

Windows Command Prompt:

```bat
venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Run

```bash
streamlit run app.py
```

Enter a Gemini API key in the sidebar. The key is used for the current app session and is not written into this repository.

## Notes and limitations

- Use a PDF with selectable text. Scanned image-only PDFs require OCR before upload.
- The first processing run sends text excerpts to Google's Gemini API to create embeddings and responses. Do not upload confidential or restricted papers unless permitted.
- Gemini API availability, quotas, and rate limits are controlled by Google. A temporary `503 UNAVAILABLE` can be retried later; it is not a code syntax error.
- Generated summaries and critiques can contain mistakes. Verify them against the original paper.
- The app builds an in-memory Chroma collection for the current upload. Re-upload the PDF after restarting the app.
- Never commit your API key, `.env` file, `venv/`, or private PDFs to GitHub.

## GitHub upload checklist

Commit:
- `app.py`
- `requirements.txt`
- `README.md`

Do not commit:
- `venv/`
- `.env`
- API keys
- downloaded private papers
- Chroma database folders

Suggested `.gitignore`:

```gitignore
venv/
.venv/
__pycache__/
*.py[cod]
.env
.chroma/
chroma_db/
.streamlit/secrets.toml
```

## Academic integrity

PaperLens is a study aid, not a substitute for reading the source paper. Cite the original paper in coursework and verify every generated claim before using it.
