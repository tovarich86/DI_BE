import streamlit as st
import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import date, timedelta, datetime
import time
import io

# --- FUNÇÃO DE SCRAPING (Corrigida para robustez) ---
def get_di_b3(data_consulta: date):
    """
    Faz o web scraping dos dados da taxa DI x pré da B3 para uma data específica.

    Args:
        data_consulta: Um objeto datetime.date representando a data da consulta.

    Returns:
        Um DataFrame do pandas com os dados da data, ou None se a consulta falhar.
    """
    data_url_display = data_consulta.strftime('%d/%m/%Y')
    data_url_query = data_consulta.strftime('%Y%m%d')

    url = (
        f"https://www2.bmf.com.br/pages/portal/bmfbovespa/lumis/"
        f"lum-taxas-referenciais-bmf-ptBR.asp"
        f"?Data={data_url_display}&Data1={data_url_query}&slcTaxa=PRE"
    )

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        tabela = soup.find('table', id='tb_principal1')

        if not tabela:
            return None

        # ✅ CORREÇÃO APLICADA AQUI
        # Encontra o corpo da tabela e verifica se ele existe antes de continuar
        tbody = tabela.find('tbody')
        if not tbody:
            return None

        dados_extraidos = []
        # Itera sobre o tbody que agora temos certeza que existe
        for linha in tbody.find_all('tr'):
            celulas = linha.find_all('td')
            if len(celulas) == 3:
                dias_corridos = celulas[0].get_text(strip=True)
                taxa_252 = celulas[1].get_text(strip=True).replace(',', '.')
                taxa_360 = celulas[2].get_text(strip=True).replace(',', '.')
                dados_extraidos.append([dias_corridos, taxa_252, taxa_360])

        if not dados_extraidos:
            return None

        df = pd.DataFrame(dados_extraidos, columns=['Dias Corridos', 'Taxa DI 252', 'Taxa DI 360'])
        df['Data Referencia'] = data_consulta
        return df

    except requests.exceptions.RequestException:
        return None

# --- FUNÇÃO PARA CONVERTER DATAFRAME PARA EXCEL ---
def to_excel(df):
    """
    Converte um DataFrame para um objeto BytesIO em formato Excel.
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Taxas_DI')
    processed_data = output.getvalue()
    return processed_data

# --- INTERFACE DA APLICAÇÃO STREAMLIT ---
st.set_page_config(page_title="B3 Scraper - Taxas DI", layout="wide")

st.title("📊 Captura de Taxas DI Pré da B3")
st.markdown("Use as opções na barra lateral para buscar as taxas para uma data específica ou para várias datas via upload de arquivo.")

# --- BARRA LATERAL PARA ENTRADA DE DADOS ---
st.sidebar.header("Opções de Busca")

st.sidebar.subheader("1. Busca por Data Única")
data_selecionada = st.sidebar.date_input("Selecione a data", date.today())

st.sidebar.markdown("---")

st.sidebar.subheader("2. Busca por Lote de Datas")
arquivo_datas = st.sidebar.file_uploader(
    "Carregue um arquivo (CSV ou Excel)",
    type=['csv', 'xlsx']
)
st.sidebar.info(
    "O arquivo deve conter uma coluna chamada 'Data' com as datas no formato DD/MM/AAAA ou AAAA-MM-DD."
)

if st.sidebar.button("Buscar Dados", type="primary"):
    datas_para_buscar = []

    if arquivo_datas is not None:
        try:
            if arquivo_datas.name.endswith('.csv'):
                df_datas = pd.read_csv(arquivo_datas)
            else:
                df_datas = pd.read_excel(arquivo_datas)

            if 'Data' not in df_datas.columns:
                st.error("Erro no arquivo: A coluna 'Data' não foi encontrada. Verifique o cabeçalho.")
            else:
                datas_para_buscar = pd.to_datetime(df_datas['Data'], dayfirst=True).dt.date.tolist()
                st.info(f"Arquivo carregado com sucesso. {len(datas_para_buscar)} datas encontradas para busca.")

        except Exception as e:
            st.error(f"Não foi possível processar o arquivo. Erro: {e}")
            datas_para_buscar = []
    else:
        datas_para_buscar.append(data_selecionada)

    if datas_para_buscar:
        lista_de_dataframes = []
        barra_progresso = st.progress(0, text="Iniciando busca...")

        with st.spinner("Aguarde, capturando os dados..."):
            for i, data_atual in enumerate(datas_para_buscar):
                percentual_completo = (i + 1) / len(datas_para_buscar)
                barra_progresso.progress(percentual_completo, text=f"Buscando dados para: {data_atual.strftime('%d/%m/%Y')}")

                df_diario = get_di_b3(data_atual)
                if df_diario is not None:
                    lista_de_dataframes.append(df_diario)

                time.sleep(0.3)

            barra_progresso.empty()

        if lista_de_dataframes:
            df_final = pd.concat(lista_de_dataframes, ignore_index=True)

            for col in ['Dias Corridos', 'Taxa DI 252', 'Taxa DI 360']:
                df_final[col] = pd.to_numeric(df_final[col])

            df_final = df_final[['Data Referencia', 'Dias Corridos', 'Taxa DI 252', 'Taxa DI 360']]

            st.success("Busca concluída com sucesso!")
            st.dataframe(df_final)

            df_excel = to_excel(df_final)
            nome_arquivo_download = f"taxas_di_b3_{date.today().strftime('%Y%m%d')}.xlsx"

            st.download_button(
                label="📥 Baixar Dados em Excel",
                data=df_excel,
                file_name=nome_arquivo_download,
                mime="application/vnd.ms-excel"
            )
        else:
            st.warning("Nenhum dado foi encontrado para as datas fornecidas. (Verifique se são dias úteis).")
