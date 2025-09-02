# app.py — 美化与功能增强版（长条 logo 放大版）
import os
import io
import re
import json
import base64
from pathlib import Path
from typing import List, Tuple

import pandas as pd
import networkx as nx
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image
import qrcode

# ---------------- basic config ----------------
st.set_page_config(
    page_title="🧬 数绘师道 · 五老精神 系谱平台",
    layout="wide",
    initial_sidebar_state="expanded"
)

ROOT = Path.cwd()
DATA_DIR = ROOT / "data"
AVATAR_DIR = ROOT / "static" / "avatars"
EXPORT_DIR = ROOT / "exports"
DATA_DIR.mkdir(exist_ok=True)
AVATAR_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

PLACEHOLDER = ("data:image/png;base64,"
               "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII=")

# 主题色：深红 + 更亮金色
THEME = {
    "accent": "#8B0000",   # 深红
    "edge": "#8b4513",     # 棕边
    "bg": "#8B0000",       # 页面纯红背景（默认）
    "gold": "#FFD60A",     # 更亮的金色
    "yellow": "#FFD800"    # 黄色（副标题）
}

# 五老精神（带简短说明，用于左侧导出说明）
WULAO = {
    "忠诚": "对党和人民事业无限忠诚，矢志不渝",
    "关爱": "关心下一代成长，无私奉献爱心",
    "创新": "勇于探索，推动工作创新发展",
    "奉献": "无私奉献，不计个人得失",
    "务实": "脚踏实地，注重实际成效"
}
WULAO_KEYWORDS = list(WULAO.keys())

# ---------------- helpers ----------------
def safe_read_csv(path: Path) -> pd.DataFrame:
    if path.exists():
        try:
            return pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()

def img_to_base64(path: str) -> str:
    """将图片文件转为 data:...;base64, 若失败返回占位图"""
    if not path:
        return PLACEHOLDER
    p = Path(path)
    if not p.exists():
        return PLACEHOLDER
    ext = p.suffix.lower()
    mime = "image/png" if ext == ".png" else "image/jpeg"
    try:
        with open(p, "rb") as f:
            b = base64.b64encode(f.read()).decode("utf-8")
        return f"data:{mime};base64,{b}"
    except Exception:
        return PLACEHOLDER

def pil_resize_and_save(file_bytes: bytes, out_path: Path, max_w=1600, max_h=1200, quality=85):
    """调整并保存图片（用于上传背景 / 头像 / logo）"""
    img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    img.thumbnail((max_w, max_h), Image.LANCZOS)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="JPEG", quality=quality, optimize=True)
    return out_path

def find_avatar_path(avatar_field: str) -> str:
    """尝试从绝对路径、static/avatars、data/、ROOT 中寻找头像文件"""
    if not avatar_field or not str(avatar_field).strip():
        return ""
    p = Path(str(avatar_field))
    if p.is_absolute() and p.exists():
        return str(p)
    # try static avatars
    cand1 = AVATAR_DIR / str(avatar_field)
    if cand1.exists():
        return str(cand1)
    # try data/
    cand2 = DATA_DIR / str(avatar_field)
    if cand2.exists():
        return str(cand2)
    # try project root
    cand3 = ROOT / str(avatar_field)
    if cand3.exists():
        return str(cand3)
    return ""

def parse_relations(rel_df: pd.DataFrame) -> List[Tuple[str,str,str]]:
    triples = []
    if rel_df.empty:
        return triples
    cols_lower = [c.lower() for c in rel_df.columns]
    if "source" in cols_lower and "target" in cols_lower:
        df = rel_df.copy()
        df.columns = cols_lower
        for _, r in df.iterrows():
            s = str(r.get("source","")).strip()
            t = str(r.get("target","")).strip()
            rel = str(r.get("relation","")).strip() if "relation" in df.columns else ""
            if s and t:
                triples.append((s, rel or "关系", t))
        return triples
    if "描述" in rel_df.columns:
        pat = re.compile(r"([\u4e00-\u9fa5A-Za-z0-9_\-\s]{1,60})是([\u4e00-\u9fa5A-Za-z0-9_\-\s]{0,60})的([\u4e00-\u9fa5A-Za-z0-9_\-\s]{1,60})")
        for txt in rel_df['描述'].astype(str):
            m = pat.match(txt)
            if m:
                s = m.group(1).strip()
                o = m.group(2).strip()
                r = m.group(3).strip()
                if s and o:
                    triples.append((s, r, o))
    return triples

def build_graph(triples: List[Tuple[str,str,str]]) -> nx.DiGraph:
    G = nx.DiGraph()
    for s, r, t in triples:
        G.add_node(s)
        G.add_node(t)
        G.add_edge(s, t, label=r or "")
    return G

def generate_qr_for_url(url: str, out_path: Path):
    img = qrcode.make(url)
    img.save(out_path)
    return out_path

# ---------------- render vis html ----------------
def render_vis_html(G: nx.Graph, persons_df: pd.DataFrame, accent: str, edge_color: str, bg_color: str) -> str:
    nodes = []
    edges = []
    for n in G.nodes():
        row = persons_df[persons_df['name'] == n] if not persons_df.empty else pd.DataFrame()
        intro = row['intro'].iloc[0] if (not row.empty and 'intro' in row.columns) else ""
        bio = row['bio'].iloc[0] if (not row.empty and 'bio' in row.columns) else ""
        avatar_b64 = PLACEHOLDER

        if not row.empty and 'avatar' in row.columns and row['avatar'].iloc[0]:
            avatar_field = row['avatar'].iloc[0]
            realp = find_avatar_path(avatar_field)
            if realp:
                avatar_b64 = img_to_base64(realp)

        spirit_tags = []
        if isinstance(bio, str):
            for kw in WULAO_KEYWORDS:
                if kw in bio:
                    spirit_tags.append(kw)

        node_color = None
        if spirit_tags or (not row.empty and 'is_wulao' in row.columns and str(row['is_wulao'].iloc[0]).strip() == "1"):
            node_color = {"border": THEME["gold"], "background": "#fff"}

        nodes.append({
            "id": n,
            "label": n,
            "image": avatar_b64,
            "shape": "circularImage",
            "title": f"<div style='max-width:260px;font-size:13px;'><b>{n}</b><br>{intro}</div>",
            "bio": "; ".join(spirit_tags + ([bio] if bio else [])),
            "color": node_color
        })
    for u, v, d in G.edges(data=True):
        edges.append({"from": u, "to": v, "label": d.get("label",""), "arrows": "to"})
    nodes_json = json.dumps(nodes, ensure_ascii=False)
    edges_json = json.dumps(edges, ensure_ascii=False)

    template = """
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>五老精神 动态系谱图</title>
<style>
  html,body { height:100%; margin:0; background: __BG__; font-family: 'Noto Sans SC', 'Microsoft YaHei', Arial, sans-serif; color:#222; }
  #mynetwork { width:100%; height:100%; border-radius:8px; box-shadow: 0 14px 40px rgba(0,0,0,0.12); overflow:hidden; }
  .modal { position:fixed; right:18px; top:18px; width:360px; max-width:calc(100vw - 32px); background:#fff; padding:14px; border-radius:10px; box-shadow:0 12px 36px rgba(0,0,0,0.14); display:none; z-index:9999; border-left:4px solid __ACCENT__; }
  .modal img { width:110px; height:110px; border-radius:50%; object-fit:cover; border:4px solid __ACCENT__; box-shadow:0 10px 30px rgba(0,0,0,0.12); }
  .badge { display:inline-block; padding:4px 8px; margin:4px 4px 0 0; border-radius:10px; background:linear-gradient(90deg, __ACCENT__, __EDGE__); color:#fff; font-size:12px; }
</style>
<script src="https://unpkg.com/vis-network@9.1.2/dist/vis-network.min.js"></script>
</head>
<body>
  <div id="mynetwork"></div>
  <div class="modal" id="modalCard" aria-hidden="true">
    <div style="text-align:center">
      <img id="mAvatar" src="" alt="avatar"/>
      <h3 id="mName" style="margin:12px 0 6px;color:__ACCENT__"></h3>
    </div>
    <div id="mBio" style="font-size:14px;color:#222;line-height:1.6;max-height:260px;overflow:auto;"></div>
  </div>

<script>
  const nodesData = __NODES__;
  const edgesData = __EDGES__;
  const container = document.getElementById('mynetwork');
  const nodes = new vis.DataSet(nodesData);
  const edges = new vis.DataSet(edgesData);
  const data = { nodes: nodes, edges: edges };
  const options = {
    nodes: {
      shape: 'circularImage',
      size: 48,
      font: { size:14, color:'#222' },
      borderWidth: 2,
      color: { border: '__ACCENT__', background: '#fff' }
    },
    edges: {
      color: { color: '__EDGE__' },
      width: 2,
      smooth: { enabled:true, type:'dynamic' },
      font: { align: 'middle' }
    },
    interaction: { hover:true, navigationButtons:true, zoomView:true },
    physics: { enabled:true, barnesHut: { gravitationalConstant: -20000, springLength: 180, springConstant: 0.01 }, stabilization: { iterations: 250 } }
  };
  const network = new vis.Network(container, data, options);

  const modal = document.getElementById('modalCard');
  const mAvatar = document.getElementById('mAvatar');
  const mName = document.getElementById('mName');
  const mBio = document.getElementById('mBio');

  network.on('click', function(params) {
    if (params.nodes.length > 0) {
      const id = params.nodes[0];
      const node = nodes.get(id);
      mAvatar.src = node.image || '';
      mName.innerText = node.label || id;
      mBio.innerHTML = (node.bio && node.bio.length>0) ? node.bio.replace(/\\n/g, '<br/>').replace(/; /g, '<br/>') : '<i style="color:#888">暂无详细信息</i>';
      modal.style.display = 'block';
    } else {
      modal.style.display = 'none';
    }
  });

  window.addEventListener('click', function(e) {
    if (!e.target.closest('.modal') && !e.target.closest('.vis-network')) {
      modal.style.display = 'none';
    }
  });

  network.once('stabilizationIterationsDone', function() {
    try {
      const ids = nodes.getIds();
      let i = 0;
      function step() {
        if (i >= ids.length) return;
        const nid = ids[i];
        const old = nodes.get(nid);
        nodes.update({ id: nid, size: (old.size || 48) * 1.18 });
        setTimeout(()=> nodes.update({ id: nid, size: (old.size || 48) }), 650);
        i++;
        setTimeout(step, 90);
      }
      setTimeout(step, 200);
    } catch(e){ console.warn(e); }
  });
</script>
</body>
</html>
"""
    html = template.replace("__NODES__", nodes_json).replace("__EDGES__", edges_json)
    html = html.replace("__ACCENT__", accent).replace("__EDGE__", edge_color).replace("__BG__", bg_color)
    return html

# ---------------- UI helpers & CSS ----------------
def inject_app_css():
    css = f"""
    <style>
    /* 顶部横幅与卡片样式 (标题金色、放大、居中)，并留出 logo 区域 */
    .topbar {{
      display:flex; align-items:center; justify-content:center;
      padding:16px 20px; background: {THEME['accent']}; color: {THEME['gold']}; border-radius:6px; margin-bottom:10px;
      position:relative;
    }}
    .topbar .logo-area {{ position:absolute; left:20px; display:flex; align-items:center; gap:12px; }}
    /* 长条横幅 logo：高度放大为 96px，最大宽度 360px，保持纵横比 */
    .topbar .logo-area img {{ height:96px; max-width:360px; object-fit:contain; border-radius:6px; box-shadow:0 6px 18px rgba(0,0,0,0.18); }}
    .topbar .title {{ font-size:44px; font-weight:900; letter-spacing:1px; color: {THEME['gold']}; text-align:center; }}
    .subtitle {{ color:{THEME['yellow']}; text-align:center; margin-top:6px; font-weight:700; }}

    .card {{ background:#fff; padding:12px; border-radius:10px; box-shadow:0 8px 24px rgba(0,0,0,0.06); }}
    .avatar-img {{ border-radius:50%; width:96px; height:96px; object-fit:cover; border:3px solid {THEME['accent']}; }}

    /* 侧栏红底黄字 */
    [data-testid="stSidebar"] > div:first-child {{
      background: {THEME['accent']} !important;
      color: {THEME['yellow']} !important;
    }}
    [data-testid="stSidebar"] .stButton>button {{
      background: {THEME['yellow']} !important;
      color: {THEME['accent']} !important;
      border-radius:8px;
    }}

    /* 页面背景为纯红 */
    .stApp {{ background: {THEME['bg']} !important; }}
    .small-muted {{ color:#666; font-size:12px; }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# ---------------- main app ----------------
def main():
    inject_app_css()

    # header (centered gold title with logo area on left)
    st.sidebar.header("页面 & 数据设置")

    # logo chooser/upload
    st.sidebar.subheader("顶部 Logo (左上角)")
    logo_choice = st.sidebar.radio("Logo 来源", ["data 中已有", "上传文件", "不使用"], index=0)
    logo_uri = ""
    logo_path_str = ""
    if logo_choice == "data 中已有":
        logo_files = [p.name for p in DATA_DIR.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png")]
        if logo_files:
            sel_logo = st.sidebar.selectbox("选择 data/ 下的图片作为 logo（选空为不使用）", options=["（不使用）"] + logo_files, index=0)
            if sel_logo and sel_logo != "（不使用）":
                logo_path_str = str(DATA_DIR / sel_logo)
                logo_uri = img_to_base64(logo_path_str)
        else:
            st.sidebar.info("data/ 下没有可用的 logo 图片")
    elif logo_choice == "上传文件":
        up_logo = st.sidebar.file_uploader("上传 Logo (jpg/png)", type=["jpg","jpeg","png"])
        if up_logo:
            saved = pil_resize_and_save(up_logo.read(), DATA_DIR / "logo_uploaded.jpg", max_w=1200, max_h=400)
            logo_path_str = str(saved)
            logo_uri = img_to_base64(logo_path_str)
            st.sidebar.success("已上传并保存到 data/logo_uploaded.jpg")
    if logo_uri:
        st.sidebar.image(logo_uri, width=220, caption="Logo 预览")

    # Background chooser (from data folder or upload)
    st.sidebar.subheader("页面背景（可选）")
    bg_choice = st.sidebar.radio("背景来源", ["使用纯红（默认）", "data 中已有图片", "上传图片"], index=0)
    bg_data_uri = ""
    if bg_choice == "data 中已有图片":
        bg_files = [p.name for p in DATA_DIR.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png")]
        if bg_files:
            sel_bg = st.sidebar.selectbox("选择 data/ 下的图片作为背景（选空为不使用）", options=["（不使用）"] + bg_files, index=0)
            if sel_bg and sel_bg != "（不使用）":
                bg_data_uri = img_to_base64(str(DATA_DIR / sel_bg))
        else:
            st.sidebar.info("data/ 下没有可用背景图片")
    elif bg_choice == "上传图片":
        up_bg = st.sidebar.file_uploader("上传背景图片 (jpg/png)", type=["jpg","jpeg","png"], key="bg_upload")
        if up_bg:
            saved = pil_resize_and_save(up_bg.read(), DATA_DIR / "custom_bg.jpg", max_w=1600, max_h=900)
            bg_data_uri = img_to_base64(str(saved))
            st.sidebar.success("已上传并保存到 data/custom_bg.jpg")

    # avatar batch upload
    st.sidebar.subheader("头像批量上传（保存到 static/avatars/）")
    up_avatars = st.sidebar.file_uploader("选择头像（可多选）", accept_multiple_files=True, type=["jpg","jpeg","png"], key="avatars_uploader")
    if up_avatars:
        saved = []
        for f in up_avatars:
            name = Path(f.name).name
            out = AVATAR_DIR / name
            try:
                pil_resize_and_save(f.read(), out, max_w=1200, max_h=1200, quality=85)
            except Exception:
                with open(out, "wb") as wf:
                    wf.write(f.read())
            saved.append(name)
        st.sidebar.success(f"已保存 {len(saved)} 个头像到 static/avatars/（刷新页面生效）")
        st.experimental_rerun()

    st.sidebar.markdown("---")
    st.sidebar.markdown("说明：请在 data/persons.csv 的 avatar 列填写头像文件名（相对 static/avatars/）或填写头像绝对路径。")

    # load data
    persons = safe_read_csv(DATA_DIR / "persons.csv")
    relations = safe_read_csv(DATA_DIR / "relations.csv")

    # render header with logo left and title centered
    logo_img_html = f'<img src="{logo_uri}" alt="logo">' if logo_uri else ""
    st.markdown(f"""
    <div class="topbar" style="position:relative; z-index:100;">
      <div class="logo-area">{logo_img_html}</div>
      <div>
        <div class="title">数绘师道 · 五老精神 系谱平台</div>
        <div class="subtitle">传承红色基因 · 忠诚 · 关爱 · 创新 · 奉献 · 务实</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if persons.empty or relations.empty:
        st.warning("请确保 data/persons.csv 与 data/relations.csv 已准备好（头像放在 static/avatars/ 或使用绝对路径）。")
        if bg_data_uri:
            st.markdown(f"<div style='height:160px;background-image:url({bg_data_uri});background-size:cover;border-radius:8px;'></div>", unsafe_allow_html=True)
        return

    triples = parse_relations(relations)
    if not triples:
        st.error("未解析到任何关系，请检查 relations.csv（支持 source,target,relation 或 描述 列）")
        return

    G = build_graph(triples)

    # Export & Wulao intro side-by-side
    left_col, right_col = st.columns([2,1])
    with left_col:
        st.markdown("### 五老精神 — 诠释与宣言")
        cards_html = "<div style='display:flex;flex-wrap:wrap;gap:8px;'>"
        for k, v in WULAO.items():
            cards_html += f"<div style='background:{THEME['gold']};color:{THEME['accent']};padding:10px;border-radius:8px;min-width:140px;box-shadow:0 6px 18px rgba(0,0,0,0.08);'><strong>{k}</strong><div style='font-size:13px;color:#4b2b2b;margin-top:6px'>{v}</div></div>"
        cards_html += "</div>"
        st.markdown(cards_html, unsafe_allow_html=True)
        st.markdown("---")
        st.markdown("**说明**：导出 HTML 会把头像以 Base64 内联，方便放到静态托管或通过二维码分享。")
    with right_col:
        st.markdown("### 导出与分享")
        if st.button("生成单文件 HTML 并导出"):
            bg_style_value = f"url('{bg_data_uri}')" if bg_data_uri else THEME["bg"]
            html = render_vis_html(G, persons, accent=THEME["gold"], edge_color=THEME["edge"], bg_color=bg_style_value)
            out = EXPORT_DIR / "genealogy_export.html"
            out.write_text(html, encoding="utf-8")
            with open(out, "rb") as fh:
                st.download_button("⬇️ 下载 HTML 文件", data=fh, file_name=out.name, mime="text/html")
            st.success("已生成导出文件（已内联头像为 base64）")

        st.markdown("生成二维码以便分享（输入外部 URL）")
        user_url = st.text_input("外部 URL（可选）", value="")
        if user_url:
            qr_out = EXPORT_DIR / "qr_for_export.png"
            try:
                generate_qr_for_url(user_url, qr_out)
                st.image(str(qr_out), caption="二维码（扫码打开 URL）", width=180)
                with open(qr_out, "rb") as f:
                    st.download_button("⬇️ 下载二维码 PNG", data=f, file_name=qr_out.name, mime="image/png")
            except Exception as e:
                st.error(f"二维码生成失败：{e}")

    st.markdown("---")

    # render graph preview
    bg_style_value = f"url('{bg_data_uri}')" if bg_data_uri else THEME["bg"]
    html = render_vis_html(G, persons, accent=THEME["gold"], edge_color=THEME["edge"], bg_color=bg_style_value)

    st.markdown("## 互动图谱（预览）")
    components.html(html, height=720, scrolling=True)

    # person directory (no time shown)
    st.markdown("## 人物名录（从 data/persons.csv 读取头像）")
    per_row = 4
    cols = st.columns(per_row)
    for i, r in persons.iterrows():
        col = cols[i % per_row]
        avatar_field = r.get("avatar", "")
        avatar_path = find_avatar_path(avatar_field) if avatar_field else ""
        avatar_uri = img_to_base64(avatar_path) if avatar_path else PLACEHOLDER

        highlight = False
        bio = r.get('bio','') or ""
        for kw in WULAO_KEYWORDS:
            if kw in str(bio):
                highlight = True
                break
        if 'is_wulao' in r.index and str(r.get('is_wulao','')).strip() == "1":
            highlight = True
        border = THEME['gold'] if highlight else "#ddd"

        card_html = f"""
        <div class="card" style="text-align:center;border:2px solid {border};">
          <img src="{avatar_uri}" class="avatar-img" style="border-color:{border};"/>
          <div style="margin-top:8px;font-weight:700;color:{THEME['accent']};">{r.get('name','')}</div>
          <div class="small-muted" style="margin-top:6px;color:#666;">{r.get('intro','')}</div>
        </div>
        """
        col.markdown(card_html, unsafe_allow_html=True)
        with col.expander("查看详情"):
            st.markdown(f"### {r.get('name','')}")
            if avatar_path:
                st.image(avatar_path, width=220)
            st.markdown(f"**简介**: {r.get('intro','')}")
            st.markdown(f"**生平/事迹**: {r.get('bio','')}")
            st.markdown("---")

    st.caption("提示：导出的单文件 HTML 已将头像以 base64 内联，便于离线分享或放入二维码页面。若头像较多，导出文件会很大，建议压缩头像后再上传或只上传必要头像。")

if __name__ == "__main__":
    main()
