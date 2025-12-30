import io
import re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Consolidador de Produtos", layout="wide")

st.title("Consolidador de Produtos (Excel/CSV)")
st.caption(
    "Faça upload de .xlsx ou .csv, consolide por **Descrição do Produto** e baixe o resultado "
    "com abas **Completo** e **Consolidado** + opção de download em XLSX e CSV."
)

# -----------------------------
# Helpers
# -----------------------------
def _normalize_text(s: str) -> str:
    if s is None:
        return ""
    s = str(s).strip()
    s = re.sub(r"\s+", " ", s)
    return s

def _normalize_colname(c: str) -> str:
    c = _normalize_text(c).lower()
    c = c.replace("ç", "c").replace("ã", "a").replace("á", "a").replace("à", "a").replace("â", "a")
    c = c.replace("é", "e").replace("ê", "e").replace("í", "i").replace("ó", "o").replace("ô", "o").replace("ú", "u")
    c = re.sub(r"[^a-z0-9 ]+", " ", c)
    c = re.sub(r"\s+", " ", c).strip()
    return c

def _find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """
    Tenta achar a coluna do DF a partir de uma lista de candidatos (normalizados).
    Retorna o nome original da coluna no df, ou None.
    """
    norm_map = {col: _normalize_colname(col) for col in df.columns}
    inv: dict[str, list[str]] = {}
    for original, norm in norm_map.items():
        inv.setdefault(norm, []).append(original)

    # match exato primeiro
    for cand in candidates:
        if cand in inv:
            return inv[cand][0]

    # match por "contém"
    for cand in candidates:
        for norm, originals in inv.items():
            if cand in norm:
                return originals[0]
    return None

def _coerce_numeric(series: pd.Series) -> pd.Series:
    # Aceita "1.234,56" e "1234.56", além de strings vazias.
    s = series.astype(str).str.strip()
    s = s.replace({"": None, "None": None, "nan": None})
    # Remove separador de milhar (.) quando decimal é (,)
    s = s.str.replace(r"\.(?=\d{3}(\D|$))", "", regex=True)
    # Troca vírgula por ponto
    s = s.str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")

def consolidate_products(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """
    Retorna: (df_completo_padronizado, df_consolidado, info)
    """
    # Tentativas de nomes (normalizados)
    candidates_desc = ["descricao do produto", "descricao", "produto", "descricao produto", "desc produto"]
    candidates_qty = ["quantidade", "qtd", "qtde", "quant"]
    candidates_unit = ["valor unitario", "vl unitario", "valor un", "v unit", "unitario", "preco unitario"]
    candidates_total = ["valor total", "vl total", "total", "valor", "v total"]

    col_desc = _find_column(df, candidates_desc)
    col_qty = _find_column(df, candidates_qty)
    col_unit = _find_column(df, candidates_unit)
    col_total = _find_column(df, candidates_total)

    missing = [name for name, col in [
        ("Descrição do Produto", col_desc),
        ("Quantidade", col_qty),
        ("Valor Unitário", col_unit),
        ("Valor Total", col_total),
    ] if col is None]

    if missing:
        raise ValueError(
            "Não encontrei as colunas obrigatórias: "
            + ", ".join(missing)
            + ".\n\nDica: verifique o cabeçalho da planilha."
        )

    # Versão padronizada (mantém todas as colunas originais + adiciona colunas padrão)
    df_full = df.copy()
    df_full["Descrição do Produto"] = df_full[col_desc].apply(_normalize_text)
    df_full["Quantidade"] = _coerce_numeric(df_full[col_qty])
    df_full["Valor Unitário"] = _coerce_numeric(df_full[col_unit])
    df_full["Valor Total"] = _coerce_numeric(df_full[col_total])

    # Remove linhas sem descrição
    df_full = df_full[df_full["Descrição do Produto"].astype(str).str.strip().ne("")].copy()

    # Trata NaNs numéricos
    df_full["Quantidade"] = df_full["Quantidade"].fillna(0)
    df_full["Valor Total"] = df_full["Valor Total"].fillna(0)

    # Consolidação
    grouped = (
        df_full
        .groupby("Descrição do Produto", dropna=False, as_index=False)
        .agg({
            "Quantidade": "sum",
            "Valor Total": "sum",
        })
    )

    # Valor unitário médio ponderado: total / quantidade
    grouped["Valor Unitário (médio ponderado)"] = grouped.apply(
        lambda r: (r["Valor Total"] / r["Quantidade"]) if r["Quantidade"] not in (0, None) else 0,
        axis=1
    )

    # Reordena e ordena por descrição
    df_cons = grouped[[
        "Descrição do Produto",
        "Quantidade",
        "Valor Unitário (médio ponderado)",
        "Valor Total"
    ]].rename(columns={
        "Quantidade": "Quantidade Total",
        "Valor Total": "Valor Total Consolidado"
    }).sort_values("Descrição do Produto", ascending=True).reset_index(drop=True)

    # Validações
    sum_original_total = float(df_full["Valor Total"].sum())
    sum_cons_total = float(df_cons["Valor Total Consolidado"].sum())

    info = {
        "colunas_detectadas": {
            "descricao": col_desc,
            "quantidade": col_qty,
            "valor_unitario": col_unit,
            "valor_total": col_total,
        },
        "soma_total_original": sum_original_total,
        "soma_total_consolidado": sum_cons_total,
        "linhas_original": int(len(df)),
        "linhas_pos_limpeza": int(len(df_full)),
        "itens_consolidados": int(len(df_cons)),
    }

    return df_full, df_cons, info

def df_to_xlsx_bytes(df_full: pd.DataFrame, df_cons: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df_full.to_excel(writer, index=False, sheet_name="Completo")
        df_cons.to_excel(writer, index=False, sheet_name="Consolidado")

        # Ajuste simples de largura (melhora a leitura no Excel)
        for sheet_name, frame in [("Completo", df_full), ("Consolidado", df_cons)]:
            ws = writer.sheets[sheet_name]
            for i, col in enumerate(frame.columns):
                sample = frame[col].head(200).astype(str).tolist()
                max_len = max([len(str(col))] + [len(x) for x in sample])
                ws.set_column(i, i, min(max_len + 2, 60))
    return output.getvalue()

def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    # Usando ; por padrão (comum no Brasil) e UTF-8 com BOM para Excel abrir bem.
    return df.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")


# -----------------------------
# UI
# -----------------------------
uploaded = st.file_uploader("Envie a planilha (.xlsx ou .csv)", type=["xlsx", "csv"])

if uploaded:
    try:
        if uploaded.name.lower().endswith(".csv"):
            sep = st.selectbox("Separador do CSV", options=[";", ",", "\t"], index=0)
            df_in = pd.read_csv(uploaded, sep=sep, dtype=str, engine="python")
        else:
            xls = pd.ExcelFile(uploaded)
            sheet_used = st.selectbox("Selecione a aba do Excel", options=xls.sheet_names, index=0)
            df_in = pd.read_excel(xls, sheet_name=sheet_used, dtype=str)

        st.subheader("Pré-visualização (primeiras linhas)")
        st.dataframe(df_in.head(50), use_container_width=True)

        if st.button("Consolidar", type="primary"):
            df_full, df_cons, info = consolidate_products(df_in)

            st.success("Consolidação concluída!")

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Linhas (arquivo)", info["linhas_original"])
            with col2:
                st.metric("Itens consolidados", info["itens_consolidados"])
            with col3:
                st.metric("Linhas válidas", info["linhas_pos_limpeza"])

            st.caption("Colunas detectadas automaticamente:")
            st.json(info["colunas_detectadas"])

            # Checagem de soma total
            st.write(
                f"**Validação (Valor Total):** original = {info['soma_total_original']:.2f} | "
                f"consolidado = {info['soma_total_consolidado']:.2f}"
            )
            if abs(info["soma_total_original"] - info["soma_total_consolidado"]) > 0.01:
                st.warning(
                    "Atenção: a soma do Valor Total consolidado ficou diferente do original. "
                    "Isso geralmente acontece se houver valores inválidos/ausentes em alguma linha."
                )

            st.subheader("Resultado consolidado")
            st.dataframe(df_cons, use_container_width=True)

            # Downloads
            xlsx_bytes = df_to_xlsx_bytes(df_full, df_cons)
            csv_cons_bytes = df_to_csv_bytes(df_cons)

            st.subheader("Downloads")
            d1, d2 = st.columns(2)
            with d1:
                st.download_button(
                    label="⬇️ Baixar XLSX (Completo + Consolidado)",
                    data=xlsx_bytes,
                    file_name="resultado_consolidado.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            with d2:
                st.download_button(
                    label="⬇️ Baixar CSV (Consolidado)",
                    data=csv_cons_bytes,
                    file_name="consolidado.csv",
                    mime="text/csv",
                )

            # Opcional: CSV completo também
            with st.expander("Opções avançadas"):
                if st.checkbox("Disponibilizar também CSV do 'Completo'"):
                    csv_full_bytes = df_to_csv_bytes(df_full)
                    st.download_button(
                        label="⬇️ Baixar CSV (Completo)",
                        data=csv_full_bytes,
                        file_name="completo.csv",
                        mime="text/csv",
                    )

    except Exception as e:
        st.error(str(e))
        st.info(
            "Se quiser, me diga como estão nomeadas as colunas no seu arquivo (ex.: 'DESCR', 'QTD', 'VLR', etc.) "
            "que eu ajusto o mapeamento para bater com o seu padrão."
        )
else:
    st.info("Envie um arquivo para começar. Aceita .xlsx e .csv.")
