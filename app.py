import streamlit as st
import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import date
import time
import io

# --- FUNÇÃO DE SCRAPING (VERSÃO COM MÁXIMA DEPURAÇÃO) ---
def get_di_b3(data_consulta: date):
    """
    Função de scraping com depuradores detalhados para identificar o ponto de falha.
    """
    st.write("---")
    st.info(f"🕵️‍♂️ **Iniciando depuração para a data: {data_consulta.strftime('%d/%m/%Y')}**")

    # ETAPA 1: Formatação das datas para a URL
    st.write("➡️ **Etapa 1: Formatando as datas para a URL**")
    data_url_display = data_consulta.strftime('%d/%m/%Y')
    data_url_query = data_consulta.strftime('%Y%m%d')
    st.text(f"Parâmetro 'Data' (para exibição): {data_url_display}")
    st.text(f"Parâmetro 'Data1' (para consulta): {data_url_query}")
    
    # ETAPA 2: Construção da URL Final
    st.write("➡️ **Etapa 2: Construindo a URL final**")
    url = (
        f"https://www2.bmf.com.br/pages/portal/bmfbovespa/lumis/"
        f"lum-taxas-referenciais-bmf-ptBR.asp"
        f"?Data={data_url_display}&Data1={data_url_query}&slcTaxa=PRE"
    )
    st.write("URL que será chamada:")
    st.code(url, language="text")

    try:
        # ETAPA 3: Definição dos Cabeçalhos (Headers)
        st.write("➡️ **Etapa 3: Enviando a requisição com os seguintes cabeçalhos**")
        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
            'Connection': 'keep-alive', 'Host': 'www2.bmf.com.br', 'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Site': 'none', 'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
        }
        st.json(headers)
        
        # ETAPA 4: Executando a Requisição
        st.write("➡️ **Etapa 4: Executando a requisição para o servidor da B3...**")
        response = requests.get(url, headers=headers, timeout=20)
        
        # ETAPA 5: Analisando a Resposta do Servidor
        st.write("➡️ **Etapa 5: Analisando a resposta do servidor**")
        st.metric("Status da Resposta HTTP", response.status_code)
        st.write("Amostra do HTML recebido pelo script (primeiros 2000 caracteres):")
        st.code(response.text[:2000], language='html')

        response.raise_for_status()

        # ETAPA 6: Processando o HTML com BeautifulSoup
        st.write("➡️ **Etapa 6: Processando o HTML para encontrar os dados**")
        soup = BeautifulSoup(response.content, 'html.parser')
        
        st.write("🔎 Buscando a tabela com id='tb_principal1'...")
        tabela = soup.find('table', id='tb_principal1')
        if not tabela:
            st.error("❌ **FALHA:** A tabela 'tb_principal1' NÃO foi encontrada no HTML acima.")
            return None
        st.success("✅ Tabela encontrada!")

        st.write("🔎 Buscando o corpo da tabela ('tbody')...")
        tbody = tabela.find('tbody')
        if not tbody:
            st.error("❌ **FALHA:** O elemento 'tbody' NÃO foi encontrado dentro da tabela.")
            return None
        st.success("✅ Corpo da tabela ('tbody') encontrado!")

        dados_extraidos = []
        for linha in tbody.find_all('tr'):
            celulas = linha.find_all('td')
            if len(celulas) == 3:
                dias_corridos = celulas[0].get_text(strip=True)
                taxa_252 = celulas[1].get_text(strip=True).replace(',', '.')
                taxa_360 = celulas[2].get_text(strip=True).replace(',', '.')
                dados_extraidos.append([dias_corridos, taxa_252, taxa_360])

        if not dados_extraidos:
            st.warning("⚠️ **AVISO:** Tabela e tbody encontrados, mas sem linhas de dados (<tr>) dentro.")
            return None
        
        st.success(f"🎉 **SUCESSO:** {len(dados_extraidos)} linhas de dados extraídas!")
        df = pd.DataFrame(dados_extraidos, columns=['Dias Corridos', 'Taxa DI 252', 'Taxa DI 360'])
        df['Data Referencia'] = data_consulta
        return df

    except requests.exceptions.RequestException as e:
        st.error(f"❌ **ERRO CRÍTICO NA REQUISIÇÃO:** {e}")
        return None

# (O resto do seu código permanece igual)
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
data_selecionada = st.sidebar.date_input("Selecione a data", date.today())
st.sidebar.markdown("---")
st.sidebar.subheader("2. Busca por Lote de Datas")
arquivo_datas = st.sidebar.file_uploader(
    "Carregue um arquivo (CSV ou Excel)",
    type=['csv', 'xlsx']
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
        except Exception as e:
            st.error(f"Não foi possível processar o arquivo. Erro: {e}")
            datas_para_buscar = []
    else:
        datas_para_buscar.append(data_selecionada)

    if datas_para_buscar:
        lista_de_dataframes = []
        # Para o modo de depuração, é melhor não ter a barra de progresso
        # barra_progresso = st.progress(0, text="Iniciando busca...")
        with st.spinner("Aguarde, capturando os dados..."):
            for i, data_atual in enumerate(datas_para_buscar):
                df_diario = get_di_b3(data_atual)
                if df_diario is not None:
                    lista_de_dataframes.append(df_diario)
                time.sleep(0.5)

        if lista_de_dataframes:
            df_final = pd.concat(lista_de_dataframes, ignore_index=True)
            for col in ['Dias Corridos', 'Taxa DI 252', 'Taxa DI 360']:
                df_final[col] = pd.to_numeric(df_final[col])
            df_final = df_final[['Data Referencia', 'Dias Corridos', 'Taxa DI 252', 'Taxa DI 360']]
            st.success("Busca finalizada!")
            st.dataframe(df_final)
            df_excel = to_excel(df_final)
            nome_arquivo = f"taxas_di_b3_{date.today().strftime('%Y%m%d')}.xlsx"
            st.download_button(
                label="📥 Baixar Dados em Excel",
                data=df_excel,
                file_name=nome_arquivo,
                mime="application/vnd.ms-excel"
            )
        else:
            st.warning("Nenhum dado foi encontrado para as datas fornecidas. Verifique os logs de depuração acima para entender o motivo.")
