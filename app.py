import streamlit as st
import pandas as pd
from bs4 import BeautifulSoup
from datetime import date
import time
import io
import uuid  # <-- MUDANÇA 1: Importado para gerar nomes únicos

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

# --- FUNÇÃO DE SCRAPING COM SELENIUM (VERSÃO FINAL E ROBUSTA) ---
@st.cache_data(ttl=3600)  # Adiciona um cache de 1 hora
def get_di_b3_selenium(data_consulta: date):
    """
    Usa Selenium para simular um navegador real, com correções para evitar
    erros de sessão e garantir o encerramento do processo.
    """
    url = (
        f"https://www2.bmf.com.br/pages/portal/bmfbovespa/lumis/"
        f"lum-taxas-referenciais-bmf-ptBR.asp"
        f"?Data={data_consulta.strftime('%d/%m/%Y')}&Data1={data_consulta.strftime('%Y%m%d')}&slcTaxa=PRE"
    )

    driver = None  # Inicializa o driver como None
    try:
        options = Options()
        options.add_argument("--disable-gpu")
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        
        # <-- MUDANÇA 2: Adiciona um diretório de usuário único para cada execução
        options.add_argument(f'--user-data-dir=/tmp/selenium_{uuid.uuid4()}')

        service = Service()
        driver = webdriver.Chrome(service=service, options=options)
            
        driver.get(url)
        time.sleep(2)
        html_content = driver.page_source

        # O restante do código de scraping continua aqui dentro do 'try'
        soup = BeautifulSoup(html_content, 'html.parser')
        tabela = soup.find('table', id='tb_principal1')
        if not tabela: return None
        tbody = tabela.find('tbody')
        if not tbody: return None

        dados_extraidos = []
        for linha in tbody.find_all('tr'):
            celulas = linha.find_all('td')
            if len(celulas) == 3:
                dias = celulas[0].get_text(strip=True)
                taxa_252 = celulas[1].get_text(strip=True).replace(',', '.')
                taxa_360 = celulas[2].get_text(strip=True).replace(',', '.')
                dados_extraidos.append([dias, taxa_252, taxa_360])

        if not dados_extraidos: return None

        df = pd.DataFrame(dados_extraidos, columns=['Dias Corridos', 'Taxa DI 252', 'Taxa DI 360'])
        df['Data Referencia'] = data_consulta
        return df

    except Exception as e:
        st.error(f"Ocorreu um erro com o Selenium: {e}")
        st.info("Isso pode ocorrer na primeira execução enquanto o ambiente se ajusta. Tente recarregar a página.")
        return None
        
    finally:
        # <-- MUDANÇA 3: Bloco 'finally' garante que o driver sempre será encerrado
        if driver:
            driver.quit()

# --- O RESTO DO CÓDIGO PERMANECE IGUAL ---

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Taxas_DI')
    return output.getvalue()

st.set_page_config(page_title="B3 Scraper - Taxas DI", layout="wide")
st.title("📊 Captura de Taxas DI Pré da B3")
st.markdown("Use as opções na barra lateral para buscar as taxas.")

st.sidebar.header("Opções de Busca")
st.sidebar.subheader("1. Busca por Data Única")
data_selecionada = st.sidebar.date_input("Selecione a data", date.today())
st.sidebar.markdown("---")
st.sidebar.subheader("2. Busca por Lote de Datas")
arquivo_datas = st.sidebar.file_uploader(
    "Carregue um arquivo (CSV ou Excel)", type=['csv', 'xlsx']
)
st.sidebar.info("O arquivo deve conter uma coluna chamada 'Data' com as datas no formato DD/MM/AAAA ou AAAA-MM-DD.")

if st.sidebar.button("Buscar Dados", type="primary"):
    datas_para_buscar = []
    if arquivo_datas is not None:
        try:
            df_datas = pd.read_csv(arquivo_datas) if arquivo_datas.name.endswith('.csv') else pd.read_excel(arquivo_datas)
            if 'Data' not in df_datas.columns:
                st.error("Erro no arquivo: A coluna 'Data' não foi encontrada.")
            else:
                datas_para_buscar = pd.to_datetime(df_datas['Data'], dayfirst=True).dt.date.tolist()
                st.info(f"Arquivo carregado. {len(datas_para_buscar)} datas encontradas.")
        except Exception as e:
            st.error(f"Não foi possível processar o arquivo. Erro: {e}")
            datas_para_buscar = []
    else:
        datas_para_buscar.append(data_selecionada)

    if datas_para_buscar:
        lista_de_dataframes = []
        with st.spinner("Aguarde, o Selenium está inicializando e buscando os dados..."):
            for data_atual in datas_para_buscar:
                st.write(f"Buscando dados para: {data_atual.strftime('%d/%m/%Y')}...")
                df_diario = get_di_b3_selenium(data_atual)
                if df_diario is not None:
                    lista_de_dataframes.append(df_diario)
                else:
                    st.warning(f"Nenhum dado encontrado para {data_atual.strftime('%d/%m/%Y')}.")

        if lista_de_dataframes:
            df_final = pd.concat(lista_de_dataframes, ignore_index=True)
            for col in ['Dias Corridos', 'Taxa DI 252', 'Taxa DI 360']:
                df_final[col] = pd.to_numeric(df_final[col])
            df_final = df_final[['Data Referencia', 'Dias Corridos', 'Taxa DI 252', 'Taxa DI 360']]
            st.success("Busca concluída com sucesso!")
            st.dataframe(df_final)
            df_excel = to_excel(df_final)
            nome_arquivo = f"taxas_di_b3_{date.today().strftime('%Y%m%d')}.xlsx"
            st.download_button(
                label="📥 Baixar Dados em Excel",
                data=df_excel, file_name=nome_arquivo, mime="application/vnd.ms-excel"
            )
        else:
            st.error("Nenhum dado foi capturado para as datas fornecidas após a execução.")
