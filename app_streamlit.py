"""
app_streamlit.py — Painel do gerente: administração das Ordens de Serviço
Assistência Técnica de Computadores

Execução:
    pip install streamlit supabase pandas python-dotenv truststore
    streamlit run app_streamlit.py

Credenciais (NUNCA no código) — use UMA das opções:
  1) Arquivo .env na mesma pasta deste arquivo:
        SUPABASE_URL=https://seu-projeto.supabase.co
        SUPABASE_KEY=sua_chave
  2) Arquivo .streamlit/secrets.toml:
        SUPABASE_URL = "https://seu-projeto.supabase.co"
        SUPABASE_KEY = "sua_chave"
"""

import os
from pathlib import Path

# Usa os certificados do Windows (necessário em rede corporativa com proxy)
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Painel de Ordens de Serviço", page_icon="🛠️", layout="wide")

# ---------------------------------------------------------------------------
# Credenciais: .env  ->  .streamlit/secrets.toml  ->  variáveis de ambiente
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env", encoding="utf-8-sig")
except ImportError:
    pass

for _nome in ("SUPABASE_URL", "SUPABASE_KEY"):
    if not os.environ.get(_nome):
        try:
            if _nome in st.secrets:
                os.environ[_nome] = str(st.secrets[_nome])
        except Exception:
            pass  # secrets.toml não existe

if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_KEY"):
    st.error(
        "Credenciais não encontradas. Crie um arquivo **.env** (ou **.streamlit/secrets.toml**) "
        "na pasta do projeto com `SUPABASE_URL` e `SUPABASE_KEY`."
    )
    st.stop()

# --- Código de conexão solicitado -------------------------------------------
from supabase import create_client
import os
url = os.environ["SUPABASE_URL"]
key = os.environ["SUPABASE_KEY"]
# ----------------------------------------------------------------------------


@st.cache_resource
def conectar(url: str, key: str):
    return create_client(url, key)


supabase = conectar(url, key)

# Nomes das tabelas/colunas — ajuste aqui se o seu schema.sql usar outros nomes
TABELA_CLIENTES = "clientes"
TABELA_OS = "ordens_servico"
STATUS_OPCOES = ["Aberto", "Em andamento", "Aguardando peça", "Concluído", "Entregue", "Cancelado"]


# ---------------------------------------------------------------------------
# Acesso aos dados
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60, show_spinner="Carregando dados...")
def carregar_clientes() -> pd.DataFrame:
    resp = supabase.table(TABELA_CLIENTES).select("*").order("nome").execute()
    return pd.DataFrame(resp.data)


@st.cache_data(ttl=60, show_spinner="Carregando ordens de serviço...")
def carregar_ordens() -> pd.DataFrame:
    """Ordens de serviço já combinadas com os dados do cliente."""
    ordens = pd.DataFrame(
        supabase.table(TABELA_OS).select("*").order("id", desc=True).execute().data
    )
    clientes = carregar_clientes()
    if ordens.empty:
        return ordens

    if not clientes.empty:
        cli = clientes.rename(columns={
            "id": "cliente_id", "nome": "cliente", "email": "email",
            "celular": "celular", "endereco": "endereco",
        })
        cols = [c for c in ["cliente_id", "cliente", "email", "celular", "endereco"] if c in cli.columns]
        ordens = ordens.merge(cli[cols], on="cliente_id", how="left")

    ordens = ordens.rename(columns={"id": "os"})
    preferidas = ["os", "status", "cliente", "email", "celular", "endereco",
                  "modelo_computador", "problema", "data_abertura", "created_at", "cliente_id"]
    ordem_cols = [c for c in preferidas if c in ordens.columns] + \
                 [c for c in ordens.columns if c not in preferidas]
    return ordens[ordem_cols]


def recarregar():
    st.cache_data.clear()


def mensagem_pendente():
    """Mostra a mensagem guardada antes do st.rerun()."""
    msg = st.session_state.pop("_msg", None)
    if msg:
        tipo, texto = msg
        getattr(st, tipo)(texto)


def avisar_e_recarregar(tipo: str, texto: str):
    st.session_state["_msg"] = (tipo, texto)
    recarregar()
    st.rerun()


# ---------------------------------------------------------------------------
# Cabeçalho e carregamento
# ---------------------------------------------------------------------------
st.title("🛠️ Painel de Ordens de Serviço")
st.caption("Administração de clientes e ordens de serviço da assistência técnica.")
mensagem_pendente()

try:
    df_os = carregar_ordens()
    df_cli = carregar_clientes()
except Exception as e:
    st.error(f"Erro ao consultar o Supabase: {e}")
    st.stop()

extras = sorted(set(df_os["status"].dropna()) - set(STATUS_OPCOES)) if not df_os.empty else []
status_existentes = STATUS_OPCOES + extras

# ---------------------------------------------------------------------------
# Barra lateral: filtros
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("🔎 Filtros")
    f_nome = st.text_input("Nome do cliente", placeholder="Parte do nome")
    f_email = st.text_input("E-mail", placeholder="Parte do e-mail")
    f_status = st.multiselect("Status", status_existentes, placeholder="Todos")
    st.divider()
    if st.button("🔄 Atualizar dados", use_container_width=True):
        recarregar()
        st.rerun()

df_filtrado = df_os.copy()
if not df_filtrado.empty:
    if f_nome:
        df_filtrado = df_filtrado[df_filtrado["cliente"].fillna("").str.contains(f_nome, case=False, regex=False)]
    if f_email:
        df_filtrado = df_filtrado[df_filtrado["email"].fillna("").str.contains(f_email, case=False, regex=False)]
    if f_status:
        df_filtrado = df_filtrado[df_filtrado["status"].isin(f_status)]

aba_consultar, aba_cadastrar, aba_editar, aba_indicadores = st.tabs(
    ["📋 Consultar", "➕ Cadastrar", "✏️ Editar/Excluir", "📊 Indicadores"]
)

# ---------------------------------------------------------------------------
# Aba 1 — Consultar
# ---------------------------------------------------------------------------
with aba_consultar:
    st.subheader("Ordens de serviço")
    st.write(f"**{len(df_filtrado)}** de {len(df_os)} ordens exibidas (use os filtros na barra lateral).")

    if df_filtrado.empty:
        st.info("Nenhuma ordem de serviço encontrada.")
    else:
        st.dataframe(
            df_filtrado,
            use_container_width=True,
            hide_index=True,
            column_config={
                "os": st.column_config.NumberColumn("OS nº", format="%d"),
                "status": "Status",
                "cliente": "Cliente",
                "email": "E-mail",
                "celular": "Celular",
                "endereco": "Endereço",
                "modelo_computador": "Modelo",
                "problema": st.column_config.TextColumn("Problema", width="large"),
                "cliente_id": None,  # oculta a coluna técnica
            },
        )

    st.download_button(
        "⬇️ Exportar dados filtrados (CSV)",
        data=df_filtrado.to_csv(index=False, sep=";").encode("utf-8-sig"),
        file_name="ordens_de_servico.csv",
        mime="text/csv",
        disabled=df_filtrado.empty,
    )

# ---------------------------------------------------------------------------
# Aba 2 — Cadastrar
# ---------------------------------------------------------------------------
with aba_cadastrar:
    st.subheader("Nova ordem de serviço")

    tipo_cliente = st.radio("Cliente", ["Cliente existente", "Novo cliente"], horizontal=True,
                            index=0 if not df_cli.empty else 1)

    with st.form("form_nova_os", clear_on_submit=True):
        if tipo_cliente == "Cliente existente" and not df_cli.empty:
            opcoes_cli = {f"{r['nome']} — {r['email']}": r["id"] for _, r in df_cli.iterrows()}
            cli_escolhido = st.selectbox("Selecione o cliente", list(opcoes_cli.keys()))
        else:
            c1, c2 = st.columns(2)
            n_nome = c1.text_input("Nome do cliente*")
            n_email = c2.text_input("E-mail*")
            c3, c4 = st.columns(2)
            n_celular = c3.text_input("Celular/WhatsApp* (somente números)")
            n_endereco = c4.text_input("Endereço*")

        c5, c6 = st.columns(2)
        n_modelo = c5.text_input("Modelo do computador*")
        n_status = c6.selectbox("Status inicial", STATUS_OPCOES, index=0)
        n_problema = st.text_area("Problema apresentado*", height=120)

        enviar = st.form_submit_button("Cadastrar OS", type="primary")

    if enviar:
        erros = []
        if not n_modelo.strip() or not n_problema.strip():
            erros.append("Preencha o modelo do computador e o problema apresentado.")
        novo = not (tipo_cliente == "Cliente existente" and not df_cli.empty)
        if novo:
            if not all(v.strip() for v in (n_nome, n_email, n_celular, n_endereco)):
                erros.append("Preencha todos os dados do novo cliente.")
            if n_email.strip() and ("@" not in n_email or "." not in n_email.split("@")[-1]):
                erros.append("E-mail em formato inválido.")
            if n_celular.strip() and not n_celular.strip().isdigit():
                erros.append("O celular deve conter apenas números.")

        if erros:
            for e in erros:
                st.error(e)
        else:
            try:
                if novo:
                    email_norm = n_email.strip().lower()
                    existente = supabase.table(TABELA_CLIENTES).select("id").eq("email", email_norm).limit(1).execute()
                    if existente.data:
                        cliente_id = existente.data[0]["id"]
                    else:
                        cliente_id = supabase.table(TABELA_CLIENTES).insert({
                            "nome": n_nome.strip(), "email": email_norm,
                            "celular": n_celular.strip(), "endereco": n_endereco.strip(),
                        }).execute().data[0]["id"]
                else:
                    cliente_id = opcoes_cli[cli_escolhido]

                nova = supabase.table(TABELA_OS).insert({
                    "cliente_id": cliente_id,
                    "modelo_computador": n_modelo.strip(),
                    "problema": n_problema.strip(),
                    "status": n_status,
                }).execute()
                avisar_e_recarregar("success", f"✅ OS nº {nova.data[0]['id']} cadastrada com sucesso!")
            except Exception as e:
                st.error(f"Erro ao cadastrar: {e}")

# ---------------------------------------------------------------------------
# Aba 3 — Editar/Excluir
# ---------------------------------------------------------------------------
with aba_editar:
    col_os, col_cli = st.columns(2, gap="large")

    # ----- Ordem de serviço -----
    with col_os:
        st.subheader("Ordem de serviço")
        if df_os.empty:
            st.info("Não há ordens de serviço cadastradas.")
        else:
            rotulos_os = {f"OS {int(r['os'])} — {r.get('cliente', '')} ({r['status']})": int(r["os"])
                          for _, r in df_os.iterrows()}
            os_sel = rotulos_os[st.selectbox("Selecione a OS", list(rotulos_os.keys()), key="sel_os")]
            linha = df_os[df_os["os"] == os_sel].iloc[0]

            st.caption(f"**Modelo:** {linha.get('modelo_computador', '')}  \n**Problema:** {linha.get('problema', '')}")

            idx = status_existentes.index(linha["status"]) if linha["status"] in status_existentes else 0
            novo_status = st.selectbox("Novo status", status_existentes, index=idx, key="novo_status")
            if st.button("💾 Salvar status", key="btn_status"):
                try:
                    supabase.table(TABELA_OS).update({"status": novo_status}).eq("id", os_sel).execute()
                    avisar_e_recarregar("success", f"Status da OS {os_sel} alterado para **{novo_status}**.")
                except Exception as e:
                    st.error(f"Erro ao atualizar: {e}")

            st.divider()
            st.markdown("**Excluir esta OS**")
            conf_os = st.checkbox(f"Confirmo que desejo excluir a OS {os_sel} definitivamente", key=f"conf_os_{os_sel}")
            if st.button("🗑️ Excluir OS", type="primary", disabled=not conf_os, key="btn_del_os"):
                try:
                    supabase.table(TABELA_OS).delete().eq("id", os_sel).execute()
                    avisar_e_recarregar("success", f"OS {os_sel} excluída.")
                except Exception as e:
                    st.error(f"Erro ao excluir: {e}")

    # ----- Cliente -----
    with col_cli:
        st.subheader("Cliente")
        if df_cli.empty:
            st.info("Não há clientes cadastrados.")
        else:
            rotulos_cli = {f"{r['nome']} — {r['email']}": r["id"] for _, r in df_cli.iterrows()}
            cli_id = rotulos_cli[st.selectbox("Selecione o cliente", list(rotulos_cli.keys()), key="sel_cli")]
            cli = df_cli[df_cli["id"] == cli_id].iloc[0]

            with st.form(f"form_cli_{cli_id}"):
                e_endereco = st.text_input("Endereço", value=cli.get("endereco") or "")
                e_email = st.text_input("E-mail", value=cli.get("email") or "")
                e_celular = st.text_input("Celular/WhatsApp (somente números)", value=str(cli.get("celular") or ""))
                salvar_cli = st.form_submit_button("💾 Salvar dados do cliente")

            if salvar_cli:
                if not e_email.strip() or "@" not in e_email:
                    st.error("Informe um e-mail válido.")
                elif e_celular.strip() and not e_celular.strip().isdigit():
                    st.error("O celular deve conter apenas números.")
                else:
                    try:
                        supabase.table(TABELA_CLIENTES).update({
                            "endereco": e_endereco.strip(),
                            "email": e_email.strip().lower(),
                            "celular": e_celular.strip(),
                        }).eq("id", cli_id).execute()
                        avisar_e_recarregar("success", f"Dados de **{cli['nome']}** atualizados.")
                    except Exception as e:
                        st.error(f"Erro ao atualizar cliente: {e}")

            st.divider()
            qtd_os_cli = int((df_os["cliente_id"] == cli_id).sum()) if "cliente_id" in df_os.columns else 0
            st.markdown("**Excluir este cliente**")
            if qtd_os_cli:
                st.warning(f"Este cliente possui **{qtd_os_cli}** OS. Elas também serão excluídas.")
            conf_cli = st.checkbox(f"Confirmo que desejo excluir {cli['nome']} definitivamente", key=f"conf_cli_{cli_id}")
            if st.button("🗑️ Excluir cliente", type="primary", disabled=not conf_cli, key="btn_del_cli"):
                try:
                    if qtd_os_cli:
                        supabase.table(TABELA_OS).delete().eq("cliente_id", cli_id).execute()
                    supabase.table(TABELA_CLIENTES).delete().eq("id", cli_id).execute()
                    avisar_e_recarregar("success", f"Cliente **{cli['nome']}** excluído.")
                except Exception as e:
                    st.error(f"Erro ao excluir cliente: {e}")

# ---------------------------------------------------------------------------
# Aba 4 — Indicadores
# ---------------------------------------------------------------------------
with aba_indicadores:
    st.subheader("Indicadores")
    if df_os.empty:
        st.info("Sem dados para exibir.")
    else:
        contagem = df_os["status"].value_counts()
        colunas = st.columns(min(len(contagem) + 1, 6))
        colunas[0].metric("Total de OS", len(df_os))
        for i, (status, qtd) in enumerate(contagem.items(), start=1):
            colunas[i % len(colunas)].metric(status, int(qtd))

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**OS por status**")
            st.bar_chart(contagem.rename("Quantidade"), horizontal=True)
        with c2:
            st.markdown("**Clientes com mais OS**")
            if "cliente" in df_os.columns:
                top = df_os["cliente"].value_counts().head(10).rename("OS")
                st.bar_chart(top, horizontal=True)

        st.metric("Clientes cadastrados", len(df_cli))
