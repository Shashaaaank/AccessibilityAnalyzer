import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
import requests
import botocore
from botocore.config import Config
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import boto3
import json
import os
from dotenv import load_dotenv
import time
from langchain.text_splitter import RecursiveCharacterTextSplitter
import re
from lxml import etree
# Load environment variables
load_dotenv()
config = Config(
    read_timeout=900,
    connect_timeout=900,
    retries={"max_attempts": 0}
)
# Configure Bedrock client
bedrock_runtime_client = boto3.client(
    'bedrock-runtime',
    region_name=os.getenv("AWS_REGION"),
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY'),
    aws_secret_access_key=os.getenv('AWS_SECRET_KEY'),
    config=config  
)


stop_time = None
start_time = None
stop_time_llm = None
start_time_llm = None

def extract_html_and_css(url):
    global start_time
    global stop_time
    """Extracts HTML and CSS content from a webpage."""
    try:
        start_time=time.time()
        service = Service(ChromeDriverManager().install())
        options = webdriver.ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--enable-unsafe-swiftshader")
        options.add_argument("--headless")  # Run without opening a browser
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")

        driver = webdriver.Chrome(service=service, options=options)
        css_files = {}

        try:
            driver.get(url)

            # Wait for the page to load fully before extracting HTML
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            except TimeoutException:
                raise Exception("Page took too long to load.")

            raw_html_content = driver.page_source.strip()

            # Ensure html_content is valid
            if not raw_html_content:
                raise Exception("Failed to retrieve HTML content.")

            soup = BeautifulSoup(raw_html_content, "html.parser")

            # for script_tag in soup.find_all("script"):
            #     script_tag.extract()  # Removes the script tag and its contents

            for tag in soup(["script", "style", "link"]):
                tag.extract()  

            html_content = soup.prettify()

            # for link in soup.find_all("link", rel="stylesheet"):
            #     css_url = link.get("href")
            #     if css_url:
            #         absolute_css_url = urljoin(url, css_url)
            #         if absolute_css_url != "https://www.dsm-firmenich.com/etc.clientlibs/dsm/clientlibs/dsm-firmenich-v1/clientlib-base.lc-ab40a8fbc31b462439c0f33d951b731d-lc.min.css":
            #         # Filter to get only the "main" CSS file
            #             css_filename = os.path.basename(urlparse(css_url).path) or "style.css"
                        
            #             # Define filters to exclude unnecessary CSS files
            #             if not css_filename.lower().startswith(("theme", "font", "icons", "bootstrap", "jquery", "normalize", "tailwind", "animation")):
            #                 try:
            #                     css_response = requests.get(absolute_css_url, timeout=10)
            #                     if css_response.status_code == 200:
            #                         css_files[css_filename] = css_response.text
            #                 except requests.RequestException as e:
            #                     print(f"Error downloading CSS {css_url}: {e}")  # Use logging instead of st.error if not in Streamlit


        finally:
            driver.quit()
            stop_time = time.time()

        #     print("\n[DEBUG] Extracted HTML Content:\n", html_content[:500])  # Print first 500 chars
        # for filename, css in css_files.items():
        #     print(f"\n[DEBUG] Extracted CSS ({filename}):\n", css[:500])  # Print first 500 chars

        # return html_content, css_files
        return html_content

    except WebDriverException as e:
        raise Exception(f"WebDriver error: {e}")
    except Exception as e:
        raise Exception(f"Extraction error: {e}")

def chunk_text(text, chunk_size=4000, chunk_overlap=100):
    # Initialize the TextSplitter from LangChain
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, 
        chunk_overlap=chunk_overlap
    )
    # text_splitter = CharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    # Split the text into chunks
    chunks = text_splitter.split_text(text)
    return chunks

def analyze_web_content(html_content):
    """Analyzes HTML and CSS together with chunking."""
    global start_time_llm
    global stop_time_llm
    try:
        start_time_llm=time.time()
        # css_content = "\n\n".join([f"CSS ({filename}):\n{content}" for filename, content in css_files.items()])
        full_content = f"HTML:\n{html_content}"


        # chunks = text_splitter.create_documents([full_content])
        
        chunks = chunk_text(full_content)
        
        final_report = ""
        
        for idx, chunk in enumerate(chunks, 1):
            print("chunk----------------------------------",idx,"--------------------")
            primer = f""" You are an expert in web accessibility analysis focusing on HTML and CSS improvements.
        Task: Analyze the following web content for accessibility issues according to WCAG 2.2 standards and Figma.After each issue description,severity and fix, provide Current code and Updated code for the same issue.Always end issue block by appending given html code "<hr style="border: 1px dashed #6082B6; width: 100%; margin: 20px 0;">
        <Example>
        Issue Description: The <a> tag is missing an accessible name.
        Severity: Critical
        Fix: Add an aria-label attribute to the <a> tag.
        Current code: <a href="https://www.example.com">Click here</a>
        Updated code: <a href="https://www.example.com" aria-label="Link to example.com">Click here</a>
        </Example>

        Response Format:
        - **Issue Description**: Only necessary accessibility issue (use bullet points `- ` before each issue).
        - **Severity**: Assign Critical, High, Medium, Low.
        - **Fix:** Provide precise code fixes.
        - **Current code:** Provide related part of existing code.
        - **Updated Code:** Modify only accessibility-related parts while keeping the structure intact.
        - **Always end report by appending "<hr style="border: 1px dashed #6082B6; width: 100%; margin: 20px 0;"> html code.

        **IMPORTANT:**
        - Ensure clear formatting for readability.
        - Do not update the href or src values while providing updated code.
        - Provide **only necessary code modifications** for Critical and High severity issues.
         
        - Provide me consolidate html code at the end of report inside <code></code> tag after updating the code mentioned inside **Updated Code:**.
        - Do not add "consolidated HTML" text in the reponse.
        **Code to Analyze:**
    {chunk}"""
        
            # prompt = f"\n\nHuman: {primer}\n\n<prompt>{system_prompt}</prompt>\n\nAssistant:\n\n"

            body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 6000,
            "temperature": 0.1,
            "messages": [
                    {
                    "role": "user",
                    "content": primer
                    }
                ]
            })

            response = bedrock_runtime_client.invoke_model(
                body=body,
                modelId="anthropic.claude-3-sonnet-20240229-v1:0",
                accept="application/json",
                contentType="application/json"
            )

            response_body = json.loads(response['body'].read())
            generated_text = response_body["content"][0].get("text", "No text found")

            if generated_text:
                final_report += "Report No:"+ str(idx) + "\n\n"+ "\n\n" + generated_text + "<hr>\n\n"
            else:
                final_report += "No relevant issues found.\n\n"

        stop_time_llm=time.time()
        print(f"Final Report Task completed in-----------------------"+final_report)
        return final_report
    
    except Exception as e:
        raise Exception(f"Web Content Analysis error: {e}")

import os

def generate_final_html(html_content, updated_codes):
    try:

        # css_content = "\n\n".join([f"CSS ({filename}):\n{content}" for filename, content in css_files.items()])
        full_content = f"Source HTML:\n{html_content}"
        
        final_html = ""a
        

        prompt = f""" You are a html code generator assistant. 
        Your task is to accurately find the specified tag and class in the {full_content} and apply the code updates given in {updated_codes}. 
        Ensure that no extra tags or attributes are added beyond those specified.Once all the updates are made provide final html in the response
        in the <HTML> tag.

**Instructions**:
1. **Update only the attributes or tags** as given in updated code.
3. **Do not add any extra tags or attributes** beyond what is specified in the updated code.
4. Maintain the existing structure of the HTML elements
"""
        
            # prompt = f"\n\nHuman: {primer}\n\n<prompt>{system_prompt}</prompt>\n\nAssistant:\n\n"

        body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 6000,
        "temperature": 0.1,
        "messages": [
                {
                "role": "user",
                "content": prompt
                }
            ]
        })

        response = bedrock_runtime_client.invoke_model(
            body=body,
            modelId="anthropic.claude-3-sonnet-"PASTEYOURID"-v1:0", #paste your claude id here to use that llm
            accept="application/json",
            contentType="application/json"
        )

        response_html = json.loads(response['body'].read())
        generated_html = response_html["content"][0].get("text", "No text found")

        if generated_html:
            final_html += "\n\n" + generated_html + "<hr>\n\n"
        else:
            final_html += "No relevant issues found.\n\n"

        print(f"Final Report Task completed in-----------------------"+final_html)
        return final_html

    except Exception as e:
        raise Exception(f"Web Content Analysis error: {e}")

import html
def main():
    st.set_page_config(layout="wide")
    st.markdown(
    """
    <style>
    .css-1d391kg {padding: 0; margin: 0;}
    </style>
    """,
    unsafe_allow_html=True
    )
    st.markdown("""
        <style>
               /* Remove blank space at top and bottom */ 
               .block-container {
                   padding-top: 0rem;
                   padding-bottom: 0rem;
                }

        </style>
        """, unsafe_allow_html=True)
    # st.title(':blue[Automated Web Accessibility Analyzer]')
    st.markdown(
        """
        <h1 style="text-align: center;color:#6082B6, margin-top: 0;">
            Automated Web Accessibility Analyzer
        </h1>
        """,
        unsafe_allow_html=True
    )
    col1, col2 = st.columns(2)
    # old_html_content=None
    # generated_report = None
    # with col1:
    if "html_content" not in st.session_state:
        st.session_state.html_content = None
    # if "css_files" not in st.session_state:
    #     st.session_state.css_files = {}
    if "report" not in st.session_state:
        st.session_state.report = None
    if "updated_codes" not in st.session_state:
        st.session_state.updated_codes = None
    url = st.text_input("Enter URL to analyze")

    if st.button("Analyze"):
        if url:
            with st.spinner("Processing..."):
                try:
                    html_content = extract_html_and_css(url)
                    elapsed_time = stop_time - start_time
                    print(f"Web crawling Task completed in--------------------------------- {elapsed_time:.2f} seconds.")
                    st.session_state.html_content = html_content
                    # st.session_state.css_files = css_files
                    report = analyze_web_content(html_content)
                    elapsed_time_llm = stop_time_llm - start_time_llm
                    print(f"LLM Task completed in------------------------ {elapsed_time_llm:.2f} seconds.")
                    # st.session_state.report = report
                    st.session_state.report = re.sub(r'<code>.*?</code>', '', report, flags=re.DOTALL)
                    st.session_state.updated_codes = re.findall(r'<code>(.*?)</code>', report, re.DOTALL)
                    html_string = "".join(st.session_state.updated_codes)
                    st.session_state.updated_codes = html.unescape(html_string)
                    print(f"updated_codes Task completed in------------------------",st.session_state.updated_codes)
                except Exception as e:
                    st.error(f"Error: {e}")
    
    if st.session_state.html_content:
        st.subheader("Download Files")

        st.download_button(
            label="Download Source HTML",
            data=st.session_state.html_content,
            file_name="source.html",
            mime="text/html"
        )
    if st.session_state.updated_codes:
        st.download_button(
            label="Download Updated HTML",
            data=st.session_state.updated_codes,
            file_name="updated_page.html",
            mime="text/html"
        )
        # for css_filename, css_content in st.session_state.css_files.items():
        #     st.download_button(
        #         label=f"Download {css_filename}",
        #         data=css_content,
        #         file_name=css_filename,
        #         mime="text/css"
        #     )
        st.divider()
        if st.session_state.get("report"):
            st.subheader("Accessibility Analysis Report")
    st.markdown(f'<div style="background-color: #E5E4E2; padding: 10px;">{st.session_state.report}</div>', unsafe_allow_html=True)
    # with col2:
     
    #     if "updated_html_content" not in st.session_state:
    #         st.session_state.updated_codes = None
    #     if st.session_state.get("report"):
    #         st.subheader("Updated HTML")
    #         # lxml_format = generate_lxml_format(st.session_state.report)
    #         if  st.session_state.updated_codes is not None:
    #             # st.session_state.updated_html_content = generate_final_html(st.session_state.html_content,  st.session_state.updated_codes)
    #             st.download_button(
    #                 label="Download Updated HTML",
    #                 data=st.session_state.updated_codes,
    #                 file_name="updated_page.html",
    #                 mime="text/html"
    #             )
    #             st.code(st.session_state.updated_codes, language='html')
if __name__ == "__main__":
    main()
