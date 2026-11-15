"""
Painel de Monitoramento de Incêndios Florestais — São Félix do Xingu (PA)

Como rodar:
    pip install -r requirements.txt
    streamlit run painel.py

Os dados ficam na pasta "dados/" em três arquivos CSV. Você pode alimentá-los
de três formas: editando as tabelas na aba "Alimentar dados", enviando um CSV
novo pela mesma aba, ou abrindo os arquivos no Excel/LibreOffice.
"""

from pathlib import Path

import pandas as pd

PASTA = Path(__file__).parent / "dados"
COMPLETO = "ano completo"

# True  = somente visualização (use esta opção na versão publicada na internet).
# False = mostra também a aba "Alimentar dados" (use no seu computador).
SOMENTE_LEITURA = True

# Cada tabela do painel: arquivo, colunas obrigatórias e quais são numéricas.
TABELAS = {
    "Focos de calor por ano": {
        "arquivo": "focos_anuais.csv",
        "colunas": ["ano", "focos", "periodo"],
        "numericas": ["ano", "focos"],
        "ajuda": 'Uma linha por ano. Em "periodo" use "ano completo" ou um texto '
                 'como "parcial até 19 de outubro".',
    },
    "Desmatamento por ano (PRODES)": {
        "arquivo": "desmatamento_prodes.csv",
        "colunas": ["ano", "km2", "periodo"],
        "numericas": ["ano", "km2"],
        "ajuda": 'Área desmatada em km². Em "periodo" use "ano completo" ou "parcial".',
    },
    "Indicadores de contexto": {
        "arquivo": "indicadores.csv",
        "colunas": ["indicador", "valor", "unidade", "periodo", "fonte"],
        "numericas": ["valor"],
        "ajuda": "Números avulsos (área do município, % em agosto, ranking etc.). "
                 "Não mude os nomes da coluna 'indicador' que já existem.",
    },
}


# ----------------------------------------------------------------------------
# Dados e cálculos (sem interface: dá para testar e reutilizar)
# ----------------------------------------------------------------------------

def validar(df: pd.DataFrame, nome: str) -> pd.DataFrame:
    """Confere colunas e tipos de uma tabela; devolve a tabela limpa ou levanta ValueError."""
    cfg = TABELAS[nome]
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    faltando = [c for c in cfg["colunas"] if c not in df.columns]
    if faltando:
        raise ValueError(f"Faltam as colunas: {', '.join(faltando)}")
    df = df[cfg["colunas"]].dropna(how="all")
    for c in cfg["numericas"]:
        convertido = pd.to_numeric(df[c], errors="coerce")
        if convertido.isna().any():
            raise ValueError(f'A coluna "{c}" tem valores vazios ou que não são números.')
        df[c] = convertido
    if "ano" in df.columns:
        df["ano"] = df["ano"].astype(int)
        if df["ano"].duplicated().any():
            raise ValueError("Há anos repetidos na tabela.")
        df = df.sort_values("ano")
    if "periodo" in df.columns:
        df["periodo"] = df["periodo"].fillna(COMPLETO).astype(str).str.strip()
    return df.reset_index(drop=True)


def carregar(nome: str) -> pd.DataFrame:
    return validar(pd.read_csv(PASTA / TABELAS[nome]["arquivo"]), nome)


def salvar(df: pd.DataFrame, nome: str) -> None:
    PASTA.mkdir(exist_ok=True)
    validar(df, nome).to_csv(PASTA / TABELAS[nome]["arquivo"], index=False)


def variacao(atual: float, anterior: float) -> float | None:
    """Variação percentual; None se não houver base de comparação."""
    return None if not anterior else (atual / anterior - 1) * 100


def indicador(ind: pd.DataFrame, chave: str) -> float | None:
    linha = ind.loc[ind["indicador"] == chave, "valor"]
    return None if linha.empty else float(linha.iloc[0])


def resumo(focos: pd.DataFrame, desmat: pd.DataFrame, ind: pd.DataFrame) -> dict:
    """Calcula os números do topo do painel a partir das três tabelas."""
    cheios = focos[focos["periodo"] == COMPLETO]
    parciais = focos[focos["periodo"] != COMPLETO]
    r = {"media": None, "ultimo": None, "anterior": None, "parcial": None,
         "var_ano": None, "var_media": None, "densidade": None,
         "desmat": None, "desmat_ant": None, "var_desmat": None}
    if not cheios.empty:
        r["ultimo"] = cheios.iloc[-1]
        r["media"] = cheios["focos"].mean()
        r["var_media"] = variacao(r["ultimo"]["focos"], r["media"])
        area = indicador(ind, "area_km2")
        if area:
            r["densidade"] = r["ultimo"]["focos"] / area * 1000
    if len(cheios) >= 2:
        r["anterior"] = cheios.iloc[-2]
        r["var_ano"] = variacao(r["ultimo"]["focos"], r["anterior"]["focos"])
    if not parciais.empty:
        r["parcial"] = parciais.iloc[-1]
    d = desmat[desmat["periodo"] == COMPLETO]
    if not d.empty:
        r["desmat"] = d.iloc[-1]
    if len(d) >= 2:
        r["desmat_ant"] = d.iloc[-2]
        r["var_desmat"] = variacao(r["desmat"]["km2"], r["desmat_ant"]["km2"])
    return r


def br(valor: float, casas: int = 0) -> str:
    """Formata número no padrão brasileiro: 7.355 e 84.212,9."""
    return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(valor: float | None) -> str | None:
    return None if valor is None else f"{valor:+.1f}%".replace(".", ",")


# ----------------------------------------------------------------------------
# Interface
# ----------------------------------------------------------------------------

def main() -> None:
    import plotly.graph_objects as go
    import streamlit as st

    COR, COR_PARCIAL, COR_LINHA, COR_REF = "#c2410c", "#d6d3d1", "#1d4ed8", "#57534e"

    st.set_page_config(page_title="Incêndios Florestais — São Félix do Xingu",
                       page_icon="🔥", layout="wide")

    try:
        focos = carregar("Focos de calor por ano")
        desmat = carregar("Desmatamento por ano (PRODES)")
        ind = carregar("Indicadores de contexto")
    except (FileNotFoundError, ValueError) as erro:
        st.error(f"Não consegui ler os dados da pasta 'dados/': {erro}")
        st.stop()

    def layout(fig, titulo_y):
        fig.update_layout(height=340, margin=dict(l=10, r=10, t=10, b=10),
                          separators=",.", hovermode="x unified",
                          legend=dict(orientation="h", y=-0.18),
                          yaxis_title=titulo_y, xaxis_title=None)
        fig.update_yaxes(tickformat=",.0f")
        fig.update_xaxes(dtick=2 if fig.data and len(fig.data[0].x) > 12 else 1)
        return fig

    # ---- Barra lateral: filtros --------------------------------------------
    with st.sidebar:
        st.header("Filtros")
        a_min, a_max = int(focos["ano"].min()), int(focos["ano"].max())
        if a_min < a_max:
            ini, fim = st.slider("Período", a_min, a_max, (a_min, a_max))
        else:
            ini, fim = a_min, a_max
        com_parcial = st.toggle("Mostrar ano parcial", value=True)
        st.caption("Os indicadores do topo usam sempre a série completa; "
                   "os filtros valem para os gráficos e a tabela.")

    def recorte(df):
        df = df[df["ano"].between(ini, fim)]
        return df if com_parcial else df[df["periodo"] == COMPLETO]

    st.title("🔥 Painel de Monitoramento de Incêndios Florestais")
    st.caption("São Félix do Xingu · Pará · focos de calor do satélite de referência do INPE (AQUA)")

    if SOMENTE_LEITURA:
        aba_painel, aba_sobre = st.tabs(["📊 Painel", "ℹ️ Sobre os dados"])
        aba_dados = None
    else:
        aba_painel, aba_dados, aba_sobre = st.tabs(["📊 Painel", "✏️ Alimentar dados", "ℹ️ Sobre os dados"])

    # ---- Aba 2: alimentar dados --------------------------------------------
    if aba_dados is not None:
        with aba_dados:
            st.write("Escolha a tabela, edite as células ou adicione linhas no fim, e clique em **Salvar**. "
                     "O painel se atualiza na hora.")
            nome = st.selectbox("Tabela", list(TABELAS))
            cfg = TABELAS[nome]
            st.caption(cfg["ajuda"])

            editada = st.data_editor(carregar(nome), num_rows="dynamic", hide_index=True,
                                     use_container_width=True, key=f"editor_{nome}")
            if st.button("💾 Salvar alterações", type="primary"):
                try:
                    salvar(editada, nome)
                    st.success("Dados salvos.")
                    st.rerun()
                except ValueError as erro:
                    st.error(f"Não salvei: {erro}")

            st.divider()
            st.write("**Ou substitua a tabela inteira por um arquivo CSV**")
            st.caption(f"Colunas esperadas: {', '.join(cfg['colunas'])}")
            enviado = st.file_uploader("Arquivo CSV", type="csv", key=f"upload_{nome}")
            if enviado is not None:
                try:
                    novo = validar(pd.read_csv(enviado, sep=None, engine="python"), nome)
                    st.dataframe(novo, hide_index=True, use_container_width=True)
                    if st.button("Substituir a tabela por este arquivo"):
                        salvar(novo, nome)
                        st.success("Tabela substituída.")
                        st.rerun()
                except (ValueError, pd.errors.ParserError) as erro:
                    st.error(f"Arquivo não aceito: {erro}")

    # ---- Aba 3: sobre -------------------------------------------------------
    with aba_sobre:
        st.markdown(
            "**Foco de calor** é um ponto em que o satélite detectou temperatura compatível com fogo. "
            "Não equivale a um incêndio confirmado nem mede a área queimada.\n\n"
            "- **Focos por ano:** INPE, Programa Queimadas, satélite de referência (AQUA), "
            "compilados pelo Statmapa.\n"
            "- **Desmatamento:** INPE, PRODES, compilado pelo Statmapa.\n"
            "- **Indicadores de contexto:** a fonte de cada número está na coluna *fonte* da tabela.\n\n"
            "Os dados são atualizados pelo responsável pelo painel a partir do BDQueimadas e do PRODES, do INPE."
        )


    # ---- Aba 1: painel (fica por último no código porque pode parar com st.stop) ----
    with aba_painel:
        r = resumo(focos, desmat, ind)
        c = st.columns(5)
        if r["ultimo"] is not None:
            rotulo = f"frente a {int(r['anterior']['ano'])}" if r["anterior"] is not None else ""
            c[0].metric(f"Focos em {int(r['ultimo']['ano'])}", br(r["ultimo"]["focos"]),
                        f"{pct(r['var_ano'])} {rotulo}" if r["var_ano"] is not None else None,
                        delta_color="inverse")
            c[2].metric("Média anual histórica", br(r["media"]),
                        f"{pct(r['var_media'])} no último ano", delta_color="inverse")
        if r["parcial"] is not None:
            c[1].metric(f"Focos em {int(r['parcial']['ano'])}", br(r["parcial"]["focos"]))
            c[1].caption(r["parcial"]["periodo"])
        if r["densidade"] is not None:
            c[3].metric("Focos por 1.000 km²", br(r["densidade"], 2))
        if r["desmat"] is not None:
            c[4].metric(f"Desmatamento em {int(r['desmat']['ano'])}", f"{br(r['desmat']['km2'], 1)} km²",
                        f"{pct(r['var_desmat'])} frente a {int(r['desmat_ant']['ano'])}"
                        if r["var_desmat"] is not None else None, delta_color="inverse")

        f, d = recorte(focos), recorte(desmat)
        if f.empty:
            st.info("Nenhum ano no período escolhido.")
            st.stop()

        esq, dir_ = st.columns(2)

        with esq:
            st.subheader("Focos de calor por ano")
            fig = go.Figure(go.Bar(
                x=f["ano"], y=f["focos"], name="Focos",
                marker_color=[COR if p == COMPLETO else COR_PARCIAL for p in f["periodo"]],
                customdata=f["periodo"], hovertemplate="%{y:,.0f} focos (%{customdata})<extra></extra>"))
            if r["media"] is not None:
                fig.add_hline(y=r["media"], line_dash="dash", line_color=COR_REF,
                              annotation_text=f"média histórica: {br(r['media'])}")
            st.plotly_chart(layout(fig, "focos"), use_container_width=True)
            st.caption("Barras cinza são anos com contagem parcial.")

        with dir_:
            st.subheader("Tendência dos focos")
            cheios = f[f["periodo"] == COMPLETO]
            fig = go.Figure()
            fig.add_scatter(x=cheios["ano"], y=cheios["focos"], mode="lines+markers", name="Focos no ano",
                            line=dict(color=COR, width=1.5), hovertemplate="%{y:,.0f}<extra>focos</extra>")
            fig.add_scatter(x=cheios["ano"], y=cheios["focos"].rolling(3).mean(), mode="lines",
                            name="Média móvel de 3 anos", line=dict(color=COR_LINHA, width=3),
                            hovertemplate="%{y:,.0f}<extra>média 3 anos</extra>")
            st.plotly_chart(layout(fig, "focos"), use_container_width=True)
            st.caption("A média móvel suaviza os anos extremos e mostra a direção geral.")

        esq, dir_ = st.columns(2)

        with esq:
            st.subheader("Desmatamento por ano (PRODES)")
            if d.empty:
                st.info("Sem dados de desmatamento no período.")
            else:
                fig = go.Figure(go.Scatter(
                    x=d["ano"], y=d["km2"], mode="lines+markers", name="km²",
                    line=dict(color=COR_LINHA, width=2.5), customdata=d["periodo"],
                    hovertemplate="%{y:,.1f} km² (%{customdata})<extra></extra>"))
                st.plotly_chart(layout(fig, "km²"), use_container_width=True)

        with dir_:
            st.subheader("Fogo e desmatamento lado a lado")
            junto = f.merge(d, on="ano", suffixes=("_f", "_d"))
            if junto.empty:
                st.info("Não há anos em comum entre as duas séries no período.")
            else:
                fig = go.Figure()
                fig.add_bar(x=junto["ano"], y=junto["focos"], name="Focos de calor", marker_color=COR,
                            hovertemplate="%{y:,.0f} focos<extra></extra>")
                fig.add_scatter(x=junto["ano"], y=junto["km2"], name="Desmatamento (km²)", yaxis="y2",
                                mode="lines+markers", line=dict(color=COR_LINHA, width=2.5),
                                hovertemplate="%{y:,.1f} km²<extra></extra>")
                fig.update_layout(yaxis2=dict(title="km²", overlaying="y", side="right", showgrid=False, tickformat=",.0f"))
                st.plotly_chart(layout(fig, "focos"), use_container_width=True)

        st.subheader("Quando e onde o fogo se concentra")
        percentuais = ind[ind["unidade"] == "%"]
        outros = ind[ind["unidade"] != "%"]
        esq, dir_ = st.columns(2)
        with esq:
            if not percentuais.empty:
                fig = go.Figure(go.Bar(
                    x=percentuais["valor"], y=percentuais["indicador"] + " (" + percentuais["periodo"] + ")",
                    orientation="h", marker_color=COR, text=[f"{br(v, 1)}%" for v in percentuais["valor"]],
                    textposition="auto", hovertemplate="%{x:.2f}%<extra></extra>"))
                fig.update_layout(height=220, margin=dict(l=10, r=10, t=10, b=10), separators=",.",
                                  xaxis=dict(range=[0, 100], ticksuffix="%"), yaxis=dict(autorange="reversed"))
                st.plotly_chart(fig, use_container_width=True)
        with dir_:
            st.dataframe(outros, hide_index=True, use_container_width=True)

        with st.expander("Ver tabela de focos por ano"):
            st.dataframe(f.sort_values("ano", ascending=False), hide_index=True, use_container_width=True)
            st.download_button("Baixar tabela (CSV)", f.to_csv(index=False).encode("utf-8"),
                               "focos_filtrados.csv", "text/csv")


if __name__ == "__main__":
    main()
