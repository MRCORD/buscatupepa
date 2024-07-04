import streamlit as st
import requests
import pandas as pd

import re
import time

from dotenv import load_dotenv
import os

load_dotenv()


st.title("Busca tu Pepa 💊")

backend_url = os.environ.get("BACKEND_URL")

@st.cache_data(ttl=600)
def mongo_consult(consult_body):
    try:
        response = requests.post(f"{backend_url}/v1/consult_mongo", json=consult_body)
        
        if response.status_code == 200:
            response_json = response.json()
            return response_json.get('documents', [])
        else:
            return []
    except Exception as e:
        st.error(f"An error occurred: {e}")
        return []
    

# Define the consultation bodies for MongoDB
consult_unique_drugs = {
    "db": "health",
    "collection": "medicines",
    "aggregation": [
        {"$group": {
                "_id": {
                    "searchTerm": "$searchTerm",
                    "concent": "$producto.concent",
                    "nombreFormaFarmaceutica": "$producto.nombreFormaFarmaceutica"
                }}},
        {"$sort": {
                "_id.searchTerm": 1,
                "_id.concent": 1,
                "_id.nombreFormaFarmaceutica": 1
            }},
        {"$project": {
                "_id": 0,
                "searchTerm": "$_id.searchTerm",
                "concent": "$_id.concent",
                "nombreFormaFarmaceutica": "$_id.nombreFormaFarmaceutica"
            }}
    ]
}

consult_unique_distritos = {
    "db": "peru",
    "collection": "districts",
    "aggregation": [
        {"$project": {"_id": 0, "descripcion": 1}},
        {"$sort": {"descripcion": 1}}
    ]
}


# Function to extract the numerical part of the concentration using regular expressions
def get_numerical_concent(concent):
    numbers = re.findall(r'\d+\.?\d*', concent)  # Find all numbers (integers or decimals)
    return float(numbers[0]) if numbers else 0  # Convert the first found number to float, default to 0 if none found



# Fetch unique drug and district names
unique_drugs = mongo_consult(consult_unique_drugs)

# Assuming unique_drugs is a list of dictionaries as described
for drug in unique_drugs:
    # Concatenate the required strings and add them under the new key 'formOption'
    drug['formOption'] = f"{drug['searchTerm']} {drug['concent']} [{drug['nombreFormaFarmaceutica']}]"



# Sorting the list with a custom key that handles numerical sorting for `concent`
unique_drugs = sorted(unique_drugs, key=lambda x: (
    x['searchTerm'],
    x['nombreFormaFarmaceutica'],
    get_numerical_concent(x['concent'])
))


unique_drugs_names = [doc['formOption'] for doc in unique_drugs]

unique_distritos = mongo_consult(consult_unique_distritos)
unique_distritos_names = sorted([doc['descripcion'] for doc in unique_distritos])


def display_chat_messages() -> None:
    """Print message history
    @returns None
    """
    for message in st.session_state.messages:
        with st.chat_message(message["role"],avatar="🧑‍⚕️"):
            st.markdown(message["content"])

def stream_data(string):
    for word in string.split(" "):
        yield word + " "
        time.sleep(0.09)
    
col1, col2, col3 = st.columns([0.2, 0.5, 0.2])


# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

if 'concentrations_shown' not in st.session_state:
    st.session_state['concentrations_shown'] = False 
    st.session_state['clicked_concentration'] = None

# Display chat messages from history on app rerun
display_chat_messages()

# Initialize session state variables if they don't exist
if 'greetings_shown' not in st.session_state:
    st.session_state['greetings_shown'] = False
    
if 'form_submitted' not in st.session_state:
    st.session_state['form_submitted'] = False


if not st.session_state.greetings_shown:
    
    intro_message = "¡Hola! Soy tu asistente virtual de búsqueda de medicinas en Lima. Estoy aquí para ayudarte a encontrar las medicinas que necesitas. ¿En qué puedo ayudarte hoy?"
    
    with st.chat_message("assistant", avatar="🧑‍⚕️"):
        st.write_stream(stream_data(intro_message))
        
    # Add assistant response to chat history
    st.session_state.messages.append({"role": "assistant", "content": intro_message})
    st.session_state.greetings_shown = True
    
if not st.session_state.form_submitted:
    
    consult_form = st.empty()
    
    with consult_form.form(key='consult_form'):
    
        selector_drugs = st.selectbox('Medicina', unique_drugs_names, index=None, placeholder="Selecciona la medicina...")
        selector_distritos = st.selectbox('Distrito', unique_distritos_names, index=None, placeholder="Selecciona el distrito...")
        submit = st.form_submit_button('Consultar')
        
    if submit:
        matching_item = [drug for drug in unique_drugs if drug['formOption'] == selector_drugs]
        
        requested_search = {
            "selected_drug": matching_item[0]['searchTerm'],
            "concent": matching_item[0]['concent'],
            "nombreFormaFarmaceutica": matching_item[0]['nombreFormaFarmaceutica'],
            "selected_distrito": selector_distritos
        }
        
        st.session_state.requested_search = requested_search
        
        
        with st.chat_message("user"):
            form_request = f"Quiero buscar información sobre {requested_search['selected_drug']} en el distrito {requested_search['selected_distrito']}"
            st.write_stream(stream_data(form_request))
        
        st.session_state.form_submitted = True
        st.session_state.messages.append({"role": "user", "content": form_request})
        
        consult_form.empty()
        
        

if 'db_consulted' not in st.session_state:
    st.session_state['db_consulted'] = False
    
if 'concentrations_loaded' not in st.session_state:
    st.session_state['concentrations_loaded'] = False  
    

if not st.session_state.db_consulted and 'requested_search' in st.session_state:
    
    with st.chat_message("assistant", avatar="🧑‍⚕️"):
        st.write_stream(stream_data("Déjame buscar la información que necesitas..."))
        st.session_state.messages.append({"role": "assistant", "content": "Déjame buscar la información que necesitas..."})
        
        
    #Query MongoDb
    find_filtered_drug_body = {
        "db": "health",
        "collection": "drugs",
        "query": {
            "searchTerm": st.session_state.requested_search['selected_drug'],
            "producto.concent": st.session_state.requested_search['concent'],
            "producto.nombreFormaFarmaceutica": st.session_state.requested_search['nombreFormaFarmaceutica'],
            "comercio.locacion.distrito": st.session_state.requested_search['selected_distrito']
        }
    }    

    filtered_drugs = mongo_consult(find_filtered_drug_body)
    
    #Retrieve drugs
    with st.chat_message("assistant", avatar="🧑‍⚕️"):
        total_results_message = f"""
        Hay {len(filtered_drugs)} resultados en total \n
        Dejame mostrarte donde las puedes encontrar más barato:
        """
        st.write_stream(stream_data(total_results_message))
        st.session_state.messages.append({"role": "assistant", "content": total_results_message})
        

    #Store retrieved drugs
    st.session_state.search_results = filtered_drugs
    
    sorted_filtered_drugs = sorted(
    filtered_drugs,
    key=lambda d: float(d.get('producto', {}).get('precios', {}).get('precio2', float('inf'))),
    # Using float('inf') as a default value to handle missing keys or values
    )
    
    top_3_filtered_drugs = sorted_filtered_drugs[:3]
    
    st.session_state['top3'] = top_3_filtered_drugs
    
        
    for drug in top_3_filtered_drugs:
        drug_name = drug['producto']['nombreProducto']
        drug_concent = drug['producto']['concent']
        drug_forma = drug['producto']['nombreFormaFarmaceutica']
        drug_price = drug['producto']['precios']['precio2']
        
        drug_comercio = drug['comercio']['nombreComercial']
        drug_ubicacion = drug['comercio']['locacion']['direccion']
        
        with st.chat_message("assistant", avatar="🧑‍⚕️"):

            drug_message = f"""
            🔍 {drug_name} {drug_concent} [{drug_forma}] - Precio: S/. {drug_price} \n
            {drug_comercio}: {drug_ubicacion}
            """

            st.write_stream(stream_data(drug_message))
            st.session_state.messages.append({"role": "assistant", "content": drug_message})
    
    st.session_state.db_consulted = True
