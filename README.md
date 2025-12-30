# Consolidador de Produtos (Streamlit)

App em Streamlit para:
- Upload de planilha **.xlsx** ou **.csv**
- Consolidação por **Descrição do Produto**
- Resultado em:
  - **XLSX** com 2 abas: `Completo` e `Consolidado`
  - **CSV** do consolidado (e opcionalmente do completo)

## Deploy no Streamlit Community Cloud
1. Suba este repositório no GitHub
2. Streamlit Community Cloud → **New app**
3. Selecione o repo/branch
4. Main file path: `app.py`
5. Deploy

## Colunas esperadas
A aplicação tenta detectar automaticamente:
- Descrição do Produto
- Quantidade
- Valor Unitário
- Valor Total

Se sua planilha usa nomes muito diferentes, ajuste os candidatos no arquivo `app.py` (variáveis `candidates_*`).

## Notas de compatibilidade (Streamlit Cloud)
- Incluímos `runtime.txt` fixando o Python em **3.12** para evitar builds demorados no Cloud.
- `requirements.txt` usa `pandas>=2.2.3` (wheels mais disponíveis) para acelerar o deploy.
