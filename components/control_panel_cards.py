import streamlit as st


CONTROL_PANEL_CARD_CSS = """
<style>
:root {
  --qq-control-bg: #262831;
  --qq-control-surface: #303340;
  --qq-control-surface-soft: #3a3e4c;
  --qq-control-border: #4e5261;
  --qq-control-text: #e3e6ef;
  --qq-control-muted: #a8afc1;
  --qq-control-field: #2c2f39;
  --qq-control-button: #434857;
  --qq-control-button-hover: #4e5261;
  --qq-primary-button: #7983a8;
}

div[data-testid="stButton"] > button[kind="primary"],
button[data-testid="stBaseButton-primary"],
div[data-testid="stFormSubmitButton"] > button[kind="primary"] {
  background: var(--qq-primary-button) !important;
  border-color: var(--qq-primary-button) !important;
  color: #f5f7fb !important;
}

div[data-testid="stButton"] > button[kind="primary"]:hover,
button[data-testid="stBaseButton-primary"]:hover,
div[data-testid="stFormSubmitButton"] > button[kind="primary"]:hover,
div[data-testid="stButton"] > button[kind="primary"]:active,
button[data-testid="stBaseButton-primary"]:active,
div[data-testid="stFormSubmitButton"] > button[kind="primary"]:active,
div[data-testid="stButton"] > button[kind="primary"]:focus,
button[data-testid="stBaseButton-primary"]:focus,
div[data-testid="stFormSubmitButton"] > button[kind="primary"]:focus {
  background: var(--qq-primary-button) !important;
  border-color: var(--qq-primary-button) !important;
  color: #f5f7fb !important;
  box-shadow: 0 0 0 1px rgba(121, 131, 168, 0.3) !important;
}

div[data-testid="stVerticalBlockBorderWrapper"]:has(.st-key-qqquest-control-card),
div[data-testid="stVerticalBlockBorderWrapper"]:has(div[class*="st-key-qqquest-control-card-"]) {
  background: linear-gradient(180deg, var(--qq-control-surface) 0%, var(--qq-control-bg) 100%) !important;
  border: 1px solid var(--qq-control-border) !important;
  border-radius: 16px !important;
  box-shadow: 0 14px 28px rgba(12, 14, 20, 0.28) !important;
}

div[data-testid="stVerticalBlockBorderWrapper"]:has(.st-key-qqquest-control-card) > div,
div[data-testid="stVerticalBlockBorderWrapper"]:has(div[class*="st-key-qqquest-control-card-"]) > div {
  background: transparent !important;
}

.st-key-qqquest-control-card,
div[class*="st-key-qqquest-control-card-"] {
  color: var(--qq-control-text) !important;
  background: linear-gradient(180deg, var(--qq-control-surface) 0%, var(--qq-control-bg) 100%) !important;
  border-radius: 16px !important;
  min-height: 100% !important;
}

.st-key-qqquest-control-card[data-testid="stVerticalBlockBorderWrapper"],
.st-key-qqquest-control-card [data-testid="stVerticalBlockBorderWrapper"],
div[class*="st-key-qqquest-control-card-"][data-testid="stVerticalBlockBorderWrapper"],
div[class*="st-key-qqquest-control-card-"] [data-testid="stVerticalBlockBorderWrapper"] {
  background: linear-gradient(180deg, var(--qq-control-surface) 0%, var(--qq-control-bg) 100%) !important;
  border: 1px solid var(--qq-control-border) !important;
  border-radius: 16px !important;
  box-shadow: 0 14px 28px rgba(12, 14, 20, 0.28) !important;
}

.st-key-qqquest-control-card > div,
.st-key-qqquest-control-card [data-testid="stVerticalBlockBorderWrapper"] > div,
div[class*="st-key-qqquest-control-card-"] > div,
div[class*="st-key-qqquest-control-card-"] [data-testid="stVerticalBlockBorderWrapper"] > div {
  background: transparent !important;
}

.st-key-qqquest-control-card > div > div,
div[class*="st-key-qqquest-control-card-"] > div > div {
  background: transparent !important;
}

.st-key-qqquest-control-card [data-testid="stMarkdownContainer"] *,
div[class*="st-key-qqquest-control-card-"] [data-testid="stMarkdownContainer"] * {
  color: var(--qq-control-text) !important;
}

.st-key-qqquest-control-card label,
.st-key-qqquest-control-card p,
.st-key-qqquest-control-card span,
.st-key-qqquest-control-card li,
div[class*="st-key-qqquest-control-card-"] label,
div[class*="st-key-qqquest-control-card-"] p,
div[class*="st-key-qqquest-control-card-"] span,
div[class*="st-key-qqquest-control-card-"] li {
  color: var(--qq-control-text) !important;
}

.st-key-qqquest-control-card [data-testid="stCaptionContainer"] p,
.st-key-qqquest-control-card .stCaption,
div[class*="st-key-qqquest-control-card-"] [data-testid="stCaptionContainer"] p,
div[class*="st-key-qqquest-control-card-"] .stCaption {
  color: var(--qq-control-muted) !important;
}

.st-key-qqquest-control-card div[data-baseweb="input"],
.st-key-qqquest-control-card div[data-baseweb="base-input"],
.st-key-qqquest-control-card div[data-baseweb="select"] > div,
div[class*="st-key-qqquest-control-card-"] div[data-baseweb="input"],
div[class*="st-key-qqquest-control-card-"] div[data-baseweb="base-input"],
div[class*="st-key-qqquest-control-card-"] div[data-baseweb="select"] > div {
  background: var(--qq-control-field) !important;
  border-color: var(--qq-control-border) !important;
  box-shadow: none !important;
}

.st-key-qqquest-control-card input,
.st-key-qqquest-control-card textarea,
div[class*="st-key-qqquest-control-card-"] input,
div[class*="st-key-qqquest-control-card-"] textarea {
  color: var(--qq-control-text) !important;
  -webkit-text-fill-color: var(--qq-control-text) !important;
}

.st-key-qqquest-control-card input::placeholder,
.st-key-qqquest-control-card textarea::placeholder,
div[class*="st-key-qqquest-control-card-"] input::placeholder,
div[class*="st-key-qqquest-control-card-"] textarea::placeholder {
  color: var(--qq-control-muted) !important;
  -webkit-text-fill-color: var(--qq-control-muted) !important;
}

.st-key-qqquest-control-card svg,
div[class*="st-key-qqquest-control-card-"] svg {
  fill: var(--qq-control-muted) !important;
}

.st-key-qqquest-control-card div[data-testid="stButton"] > button,
div[class*="st-key-qqquest-control-card-"] div[data-testid="stButton"] > button,
.st-key-qqquest-control-card button[data-testid="stBaseButton-secondary"],
.st-key-qqquest-control-card button[data-testid="stBaseButton-primary"],
div[class*="st-key-qqquest-control-card-"] button[data-testid="stBaseButton-secondary"],
div[class*="st-key-qqquest-control-card-"] button[data-testid="stBaseButton-primary"] {
  background: var(--qq-control-button) !important;
  color: var(--qq-control-text) !important;
  border: 1px solid #5c6172 !important;
}

.st-key-qqquest-control-card div[data-testid="stButton"] > button:hover,
div[class*="st-key-qqquest-control-card-"] div[data-testid="stButton"] > button:hover,
.st-key-qqquest-control-card button[data-testid="stBaseButton-secondary"]:hover,
.st-key-qqquest-control-card button[data-testid="stBaseButton-primary"]:hover,
div[class*="st-key-qqquest-control-card-"] button[data-testid="stBaseButton-secondary"]:hover,
div[class*="st-key-qqquest-control-card-"] button[data-testid="stBaseButton-primary"]:hover {
  background: var(--qq-control-button-hover) !important;
  border-color: #74798c !important;
}

.st-key-qqquest-control-card div[data-testid="stButton"] > button[kind="primary"],
.st-key-qqquest-control-card button[data-testid="stBaseButton-primary"],
div[class*="st-key-qqquest-control-card-"] div[data-testid="stButton"] > button[kind="primary"],
div[class*="st-key-qqquest-control-card-"] button[data-testid="stBaseButton-primary"] {
  background: var(--qq-primary-button) !important;
  border-color: var(--qq-primary-button) !important;
}

.st-key-qqquest-control-card [data-testid="stExpander"],
div[class*="st-key-qqquest-control-card-"] [data-testid="stExpander"] {
  background: rgba(255, 255, 255, 0.02) !important;
  border: 1px solid var(--qq-control-border) !important;
  border-radius: 12px !important;
}

.st-key-qqquest-control-card [data-testid="stExpander"] details,
div[class*="st-key-qqquest-control-card-"] [data-testid="stExpander"] details {
  background: transparent !important;
}
</style>
"""


def inject_control_panel_card_styles():
    """Inject shared styling for interactive control cards."""
    st.markdown(CONTROL_PANEL_CARD_CSS, unsafe_allow_html=True)


def themed_card_key(*parts):
    """Build a stable, CSS-friendly Streamlit key for themed cards."""
    safe_parts = []
    for part in parts:
        text = str(part)
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in text).strip("-")
        if safe:
            safe_parts.append(safe)
    suffix = "-".join(safe_parts) if safe_parts else "default"
    return f"qqquest-control-card-{suffix}"
