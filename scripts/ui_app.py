import streamlit as st, json, os, re
from query_law_pro import ask, LOG_PATH

def prettify(n): return re.sub(r'\.json$','',n).replace('_',' ').title()

ACT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__),"../pakistan_code_structured"))
ACTS = [f for f in os.listdir(ACT_DIR) if f.endswith(".json")]

def related(q, n=5):
    qw=set(re.findall(r'\w+',q.lower())); lst=[]
    for f in ACTS:
        title=prettify(f); tw=set(title.lower().split())
        c=len(qw&tw)
        if c>0: lst.append((f,title,c))
    return sorted(lst,key=lambda x:x[2],reverse=True)[:n]

st.set_page_config(page_title="Pakistan Law Assistant", page_icon="⚖️", layout="wide")
st.markdown("<h2 style='text-align:center;'>🇵🇰 Pakistan Law Assistant</h2>", unsafe_allow_html=True)
st.caption("Professional Hybrid Retrieval • FAISS + BM25 + GPT-4o")

st.sidebar.header("🕘 Recent Queries")
if os.path.exists(LOG_PATH):
    for l in reversed(open(LOG_PATH,"r",encoding="utf-8").readlines()[-10:]):
        try:j=json.loads(l);st.sidebar.markdown(f"• **{j['query']}**<br><small>Conf: {j['confidence']:.2f}</small>",unsafe_allow_html=True)
        except:continue
else:st.sidebar.write("No history yet.")

q=st.text_area("💬 Enter your legal question:",height=100)
urdu=st.toggle("🇵🇰 Translate Answer to Urdu")

if q.strip():
    rel=related(q)
    if rel:
        st.sidebar.markdown("### 📘 Related Acts")
        for f,t,_ in rel:
            law=os.path.splitext(f)[0]
            st.sidebar.markdown(f"[{t}](http://127.0.0.1:5002/view?law={law})",unsafe_allow_html=True)

if st.button("Ask",type="primary"):
    with st.spinner("Analyzing legal context..."):
        ans,conf,hits=ask(q,urdu=urdu,return_hits=True)

    pct=min(max(int(conf*100),0),100)
    col="#4CAF50" if pct>70 else "#FFC107" if pct>40 else "#F44336"
    st.markdown(f"### 🔍 Confidence\n<div style='background:#ddd;border-radius:10px;'><div style='background:{col};width:{pct}%;height:20px;border-radius:10px;'></div></div><p style='text-align:right'><b>{pct}%</b></p>",unsafe_allow_html=True)
    st.divider()
    st.markdown(ans,unsafe_allow_html=True)
    st.success("✅ Response generated.")

    if hits and "Top Retrieved Sections" not in ans:
        st.subheader("📚 Top Retrieved Sections:")
        for h in hits:
            law=h["meta"]["law"]; sec=h["meta"]["section_no"]
            st.markdown(f"• **[{law} §{sec}](http://127.0.0.1:5002/view?law={law}&section={sec})** — {h['meta'].get('section_title','')}",unsafe_allow_html=True)