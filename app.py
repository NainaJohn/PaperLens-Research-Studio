import os
import io
import re
import tempfile
from typing import TypedDict, List

import streamlit as st
from pypdf import PdfReader
from pptx import Presentation
from pptx.util import Inches, Pt

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_chroma import Chroma

# PaperLens: evidence-grounded research study studio
MODEL_NAME = "gemini-3.8-flash"
EMBEDDING_MODEL = "gemini-embedding-2"

st.set_page_config(page_title="PaperLens | Research Studio", page_icon="📚", layout="wide")

st.markdown("""
<style>
.main {background: #f7f8fc;}
.block-container {padding-top: 1.8rem; max-width: 1180px;}
.hero {padding: 1.25rem 1.5rem; border-radius: 18px; background: linear-gradient(115deg,#172554,#334155); color:white; margin-bottom:1rem;}
.hero h1 {color:white; margin:0;}
.hero p {color:#dbeafe; margin:.35rem 0 0 0;}
.small-note {color:#64748b; font-size:.9rem;}
</style>
<div class="hero">
<h1>📚 PaperLens — Research Study Studio</h1>
<p>Turn a research paper into an evidence-linked study guide, a viva practice session, and a presentation plan.</p>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("Workspace setup")
    api_key = st.text_input("Gemini API key", type="password", help="Your key is used only for this app session.")
    reading_level = st.selectbox("Explanation level", ["Beginner", "Undergraduate", "Advanced"])
    audience = st.selectbox("Presentation audience", ["Classmates", "Faculty", "Technical audience"])
    slide_count = st.slider("Presentation slides", 5, 12, 8)
    st.caption("Model: Gemini 3.8 Flash")
    st.caption("Embeddings: Gemini Embedding 2 + ChromaDB")

st.caption("A distinctive workflow: evidence-backed answers, paper-specific research critique, and interactive viva evaluation.")

uploaded = st.file_uploader("Upload a research paper (PDF)", type=["pdf"])
if not uploaded:
    st.info("Upload a text-based PDF to begin. Scanned PDFs without selectable text may need OCR first.")
    st.stop()

if not api_key:
    st.warning("Enter your Gemini API key in the sidebar to process the paper.")
    st.stop()

@st.cache_resource(show_spinner=False)
def build_resources(pdf_bytes: bytes, key: str):
    os.environ["GOOGLE_API_KEY"] = key
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    for i, page in enumerate(reader.pages):
        txt = page.extract_text() or ""
        if txt.strip():
            pages.append(Document(page_content=txt, metadata={"page": i + 1}))
    full_text = "\n\n".join(d.page_content for d in pages)
    if len(full_text.strip()) < 100:
        raise ValueError("I couldn't extract enough selectable text. Please use a text-based PDF, not a scanned image-only PDF.")
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
    chunks = splitter.split_documents(pages)
    embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL, google_api_key=key)
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name="paperlens_research"
    )
    llm = ChatGoogleGenerativeAI(model=MODEL_NAME, google_api_key=key)
    return full_text, vectorstore, llm

try:
    with st.spinner("Reading the paper and building its searchable knowledge base..."):
        paper_text, vectorstore, llm = build_resources(uploaded.getvalue(), api_key)
except Exception as e:
    st.error(f"Paper setup failed: {e}")
    st.stop()

# Intent routing: route a natural-language request to a task-specific workflow.
def detect_intent(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ["viva", "examiner", "ask me", "practice question"]):
        return "viva"
    if any(w in t for w in ["slide", "presentation", "ppt", "powerpoint"]):
        return "slides"
    if any(w in t for w in ["limitation", "gap", "future work", "critique", "weakness"]):
        return "critique"
    if any(w in t for w in ["concept", "glossary", "terms", "explain"]):
        return "concepts"
    return "summary"

# LCEL prompt templates: concise, evidence-first, and calibrated to learner level.
answer_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are PaperLens, an academic reading assistant.
Use ONLY the supplied retrieved context for claims about this paper. If the context does not contain an answer, say so clearly.
Do not invent results, authors, datasets, metrics, or citations. Cite evidence inline as [Page N] using the page metadata.
Explanation level: {level}. Task: {task}.
Structure the answer with useful headings and concise bullets. Distinguish the paper's claims from your interpretation."""),
    ("human", "User request: {question}\n\nRetrieved paper excerpts:\n{context}")
])
answer_chain = answer_prompt | llm | StrOutputParser()

def retrieve_context(question: str, k: int = 6):
    docs = vectorstore.similarity_search(question, k=k)
    return "\n\n".join(
        f"[Page {d.metadata.get('page', '?')}]\n{d.page_content}" for d in docs
    ), docs

def run_rag(question: str, task: str):
    context, docs = retrieve_context(question)
    if not context.strip():
        return "I couldn't retrieve relevant text from the paper."
    # Agentic RAG step: inspect retrieval relevance and reformulate once if retrieval is sparse.
    if len(context) < 900:
        refined_context, refined_docs = retrieve_context(
            f"Find the exact sections, definitions, evidence, and conclusions relevant to: {question}", k=8
        )
        if len(refined_context) > len(context):
            context, docs = refined_context, refined_docs
    result = answer_chain.invoke({
        "level": reading_level,
        "task": task,
        "question": question,
        "context": context
    })
    page_refs = sorted({d.metadata.get("page", "?") for d in docs}, key=lambda x: (isinstance(x, str), str(x)))
    return result, page_refs

def make_pptx(slide_text: str, title: str):
    prs = Presentation()
    title_slide = prs.slides.add_slide(prs.slide_layouts[0])
    title_slide.shapes.title.text = title
    title_slide.placeholders[1].text = "Generated from the uploaded research paper"
    lines = [x.strip() for x in slide_text.splitlines() if x.strip()]
    sections = []
    current_title = "Key points"
    current_bullets = []
    for line in lines:
        clean = re.sub(r"^[#*\-\d.)\s]+", "", line).strip()
        if not clean:
            continue
        if line.startswith("#") or (line.endswith(":") and len(clean) < 90):
            if current_bullets:
                sections.append((current_title, current_bullets))
            current_title, current_bullets = clean.rstrip(":"), []
        else:
            current_bullets.append(clean[:240])
    if current_bullets:
        sections.append((current_title, current_bullets))
    if not sections:
        sections = [("Research overview", lines[:6])]
    for heading, bullets in sections[:12]:
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = heading[:80]
        tf = slide.placeholders[1].text_frame
        tf.clear()
        for i, bullet in enumerate(bullets[:6]):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = bullet
            p.level = 0
            p.font.size = Pt(20)
    output = io.BytesIO()
    prs.save(output)
    output.seek(0)
    return output

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Paper overview", "Evidence Q&A", "Research critique", "Viva practice", "Presentation builder"
])

with tab1:
    st.subheader("Paper overview")
    st.write(f"Extracted approximately **{len(paper_text.split()):,} words** from the PDF.")
    if st.button("Generate structured study guide", key="overview"):
        with st.spinner("Building your study guide..."):
            result = run_rag(
                "Summarize this paper: research problem, motivation, objectives, method, main findings, conclusion, and important terminology.",
                "Create a structured study guide with problem, motivation, objectives, method, findings, conclusion, and key terms."
            )
        st.markdown(result[0])
        st.caption("Retrieved evidence pages: " + ", ".join(map(str, result[1])))

with tab2:
    st.subheader("Ask the paper")
    question = st.text_input("Ask a question about the uploaded paper", placeholder="What problem does the paper try to solve?")
    if st.button("Find answer", key="ask") and question.strip():
        with st.spinner("Searching the paper and preparing an evidence-linked answer..."):
            result = run_rag(question, "Answer the user's question using paper evidence.")
        st.markdown(result[0])
        st.caption("Retrieved evidence pages: " + ", ".join(map(str, result[1])))

with tab3:
    st.subheader("Research critique and gap finder")
    st.write("This mode separates what the authors explicitly state from cautious questions a reader can raise.")
    if st.button("Analyse limitations and future directions", key="critique"):
        with st.spinner("Reviewing the paper's limitations and future directions..."):
            result = run_rag(
                "Identify limitations explicitly mentioned by the authors, assumptions, evidence gaps, and future research directions. Separate explicit statements from cautious reader observations.",
                "Produce a balanced research critique. Never claim a limitation is explicitly stated unless the retrieved text says so."
            )
        st.markdown(result[0])
        st.caption("Retrieved evidence pages: " + ", ".join(map(str, result[1])))

with tab4:
    st.subheader("Interactive viva examiner")
    st.write("Generate a paper-specific question, answer it yourself, and receive feedback.")
    if "viva_question" not in st.session_state:
        st.session_state.viva_question = ""
    if "viva_feedback" not in st.session_state:
        st.session_state.viva_feedback = ""
    if st.button("Ask me a viva question", key="new_viva"):
        with st.spinner("Preparing a question from the paper..."):
            q, _ = run_rag(
                "Create ONE clear viva question based on an important concept, method, result, or limitation in this paper. Do not provide the answer.",
                "Act as a university viva examiner. Ask one question only."
            )
        st.session_state.viva_question = q
        st.session_state.viva_feedback = ""
    if st.session_state.viva_question:
        st.info(st.session_state.viva_question)
        student_answer = st.text_area("Your answer", key="student_answer", height=130)
        if st.button("Evaluate my answer", key="evaluate") and student_answer.strip():
            with st.spinner("Evaluating your answer against the paper..."):
                feedback, _ = run_rag(
                    f"Evaluate this student's viva answer to the question: {st.session_state.viva_question}\nStudent answer: {student_answer}\nGive: score out of 10, what was correct, what is missing or inaccurate, and an improved model answer.",
                    "Evaluate fairly using the paper as evidence. Be constructive and explain corrections."
                )
            st.session_state.viva_feedback = feedback
        if st.session_state.viva_feedback:
            st.markdown(st.session_state.viva_feedback)

with tab5:
    st.subheader("Presentation builder")
    st.write(f"Target: **{slide_count} slides** · Audience: **{audience}**")
    if st.button("Create slide-by-slide presentation plan", key="slides"):
        with st.spinner("Designing your presentation..."):
            slide_result, _ = run_rag(
                f"Create a {slide_count}-slide presentation plan for {audience}. For each slide give a short title and 3-5 concise bullet points. Include title, background, problem, objectives, approach, findings, limitations, conclusion, and references only when supported by the paper.",
                "Create a coherent slide plan. Do not fabricate findings or references."
            )
        st.markdown(slide_result[0])
        pptx = make_pptx(slide_result[0], "Research Paper Presentation")
        st.download_button(
            "Download PowerPoint (.pptx)",
            data=pptx,
            file_name="PaperLens_Presentation.pptx",
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )

st.divider()
st.caption("PaperLens is an academic support prototype. Verify generated summaries, critiques, and answers against the original paper before submission or presentation.")
