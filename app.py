import streamlit as st
import pandas as pd
from bs4 import BeautifulSoup
from datetime import date
import time
import io
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# --- FUNÇÃO DE SCRAPING COM SELENIUM (À Prova de Bloqueios) ---
# O cache_data garante que não vamos rodar o Selenium (que é lento) a cada interação na tela.
# Ele só vai rodar de novo se a data da consulta mudar.
@st.cache_data
def get_di_b3_selenium(data_consulta: date):
    """
    Faz o web scraping usando Selenium para simular um navegador real e evitar bloqueios.
    """
    data_url_display = data_consulta.strftime('%d/%m/%Y')
    data_url_query = data_consulta.strftime('%Y%m%d')
    url = (
        f"https://www2.bmf.com.br/pages/portal/bmfbovespa/lumis/"
        f"lum-taxas-referenciais-bmf-ptBR.asp"
        f"?Data={data_url_display}&Data1={data_url_query}&slcTaxa=PRE"
    )

    try:
        # Configurações do Chrome para rodar no Streamlit Cloud (headless)
        options = Options()
        options.add_argument("--disable-gpu")
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        # Inicializa o driver do Chrome
        # NOTA: O Service(ChromeDriverManager().install()) é ótimo para rodar localmente,
        # mas no Streamlit Cloud, o sistema já busca o chromedriver no path.
        # Vamos manter uma lógica que funciona nos dois.
        try:
            driver = webdriver.Chrome(options=options)
        except Exception:
            # Fallback para o método com webdriver-manager se o de cima falhar
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            
        # Acessa a URL
        driver.get(url)
        
        # Aguarda um pouco para a página carregar completamente (se necessário)
        time.sleep(2) 
        
        # Pega o HTML da página depois que o navegador a renderizou
        html_content = driver.page_source
        
        # Fecha o navegador para liberar recursos
        driver.quit()

        # Agora, o processo de parse é o mesmo de antes
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
        return None

# --- FUNÇÃO PARA CONVERTER DATAFRAME PARA EXCEL ---
def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Taxas_DI')
    return output.getvalue()

# --- INTERFACE DA APLICAÇÃO STREAMLIT ---
st.set_page_config(page_title="B3 Scraper - Taxas DI", layout="wide")
st.title("📊 Captura de Taxas DI Pré da B3")
st.markdown("Use as opções na barra lateral para buscar as taxas.")

st.sidebar.header("Opções de Busca")
st.sidebar.subheader("1. Busca por Data Única")
data_selecionada = st.sidebar.date_input("Selecione a data", date(2025, 9, 12)) # Data padrão
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
                # Chama a nova função com Selenium
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
