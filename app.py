import streamlit as st
import yaml
import logging
import os
from jinja2 import Environment, FileSystemLoader, meta, nodes
from nornir import InitNornir
from nornir_scrapli.tasks import send_configs
from nornir_jinja2.plugins.tasks import template_file

# --- CONFIG ---
logging.getLogger("nornir").setLevel(logging.ERROR)
st.set_page_config(page_title="Config tool", layout="wide")
st.title("Config tool")

# --- STATE ---
if 'generated_config' not in st.session_state:
    st.session_state['generated_config'] = ""
if 'step' not in st.session_state:
    st.session_state['step'] = 1

# --- AST PARSER ---
def get_template_vars_with_defaults(platform_dir, template_name):
    env = Environment(loader=FileSystemLoader("templates"))
    try:
        template_source = env.loader.get_source(env, f"{platform_dir}/{template_name}")[0]
        ast = env.parse(template_source)
        
        all_vars = meta.find_undeclared_variables(ast)
        if 'host' in all_vars:
            all_vars.remove('host')
            
        vars_map = {v: "" for v in all_vars}

        def walk_node(node):
            if isinstance(node, nodes.Filter) and node.name == 'default':
                if isinstance(node.node, nodes.Name):
                    var_name = node.node.name
                    if node.args and isinstance(node.args[0], nodes.Const):
                        if var_name in vars_map:
                            vars_map[var_name] = node.args[0].value
            for child in node.iter_child_nodes():
                walk_node(child)

        walk_node(ast)
        return vars_map
    except Exception as e:
        return {}

# --- INVENTORY GENERATOR ---
def create_inventory_file(ip, driver_platform, username, password):
    inventory_data = {
        "lab_device": {
            "hostname": ip,
            "platform": driver_platform,
            "username": username,
            "password": password,
            "port": 22,
            "connection_options": {
                "scrapli": {
                    "timeout_socket": 10,
                    "timeout_transport": 30,
                    "timeout_ops": 60,
                    "extras": {
                        "auth_strict_key": False,
                        "transport_options": {
                            "open_cmd": [
                                "-o", "StrictHostKeyChecking=no",
                                "-o", "UserKnownHostsFile=/dev/null",
                                "-o", "KexAlgorithms=+diffie-hellman-group-exchange-sha1,diffie-hellman-group14-sha1",
                                "-o", "HostKeyAlgorithms=+ssh-rsa",
                                "-o", "PubkeyAcceptedKeyTypes=+ssh-rsa",
                                "-o", "Ciphers=+aes128-cbc,3des-cbc,aes192-cbc,aes256-cbc"
                            ]
                        }
                    }
                }
            }
        }
    }
    with open("hosts.yaml", "w") as f:
        yaml.dump(inventory_data, f)

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Device Connection")
    target_ip = st.text_input("IP Address", value="192.168.122.100")
    
    st.header("2. Authentication")
    username = st.text_input("Username", value="admin")
    password = st.text_input("Password", type="password")
    
    st.divider()

    st.header("3. Platform & Template")
    
    # Список папок, которые ты создашь в templates/
    folder_options = ["ios", "nxos", "arubaos", "arubaos-cx", "fortios"]
    selected_platform_folder = st.selectbox("Platform Family", folder_options)
    
    # --- DRIVER MAPPING LOGIC ---
    # Сопоставляем название папки с реальным именем драйвера Scrapli
    if selected_platform_folder == "ios":
        driver_platform = "cisco_iosxe"    # Стандарт Scrapli для IOS/IOS-XE
    elif selected_platform_folder == "nxos":
        driver_platform = "cisco_nxos"     # Стандарт Scrapli
    elif selected_platform_folder == "arubaos-cx":
        driver_platform = "aruba_aoscx"    # Стандарт Scrapli (AOS-CX)
    elif selected_platform_folder == "arubaos":
        driver_platform = "aruba_aoss"     # Community driver (ArubaOS-Switch / Provision)
    elif selected_platform_folder == "fortios":
        driver_platform = "fortinet_fortios" # Community driver
    else:
        driver_platform = selected_platform_folder # Fallback

    # Сканируем папку шаблонов
    try:
        available_templates = os.listdir(f"templates/{selected_platform_folder}")
    except FileNotFoundError:
        available_templates = []
        st.error(f"⚠️ Folder templates/{selected_platform_folder} missing!")
    
    selected_template = st.selectbox("Select Configuration", available_templates)

    st.divider()
    
    st.header("4. Parameters")
    dynamic_inputs = {}
    
    if selected_template:
        vars_map = get_template_vars_with_defaults(selected_platform_folder, selected_template)
        
        if not vars_map:
            st.caption("No variables in this template.")
        else:
            for var_name, default_val in vars_map.items():
                label = var_name.replace("_", " ").title()
                val = st.text_input(
                    label, 
                    value=str(default_val), 
                    key=f"dyn_{var_name}"
                )
                dynamic_inputs[var_name] = val
    
    st.divider()

    if st.button("Generate Config 🎲", type="primary"):
        if not target_ip:
            st.warning("Please enter IP Address first!")
        else:
            create_inventory_file(target_ip, driver_platform, username, password)
            try:
                nr = InitNornir(
                    runner={"plugin": "threaded", "options": {"num_workers": 1}},
                    inventory={"plugin": "SimpleInventory", "options": {"host_file": "hosts.yaml"}}
                )
                
                res = nr.run(
                    task=template_file,
                    template=f"{selected_platform_folder}/{selected_template}",
                    path="templates",
                    **dynamic_inputs
                )
                
                if res["lab_device"].failed:
                    st.error(f"Render Failed: {res['lab_device'].result}")
                else:
                    st.session_state['generated_config'] = res["lab_device"].result
                    st.session_state['step'] = 2
                    
            except Exception as e:
                st.error(f"Critical Error: {e}")

# --- MAIN WINDOW ---

if st.session_state['step'] == 2:
    st.subheader(f"📝 Reviewing: {selected_template}")
    
    final_config = st.text_area(
        "Generated CLI Commands:",
        value=st.session_state['generated_config'],
        height=450
    )
    
    col1, col2 = st.columns([1, 6])
    
    with col1:
        if st.button("🚀 Push to Device"):
            if not password:
                st.error("Authentication required!")
            else:
                with st.spinner(f"Deploying to {target_ip}..."):
                    create_inventory_file(target_ip, driver_platform, username, password)
                    
                    try:
                        nr_push = InitNornir(
                            runner={"plugin": "threaded", "options": {"num_workers": 1}},
                            inventory={"plugin": "SimpleInventory", "options": {"host_file": "hosts.yaml"}}
                        )
                        
                        push_res = nr_push.run(
                            task=send_configs,
                            configs=final_config.splitlines()
                        )
                        
                        if push_res["lab_device"].failed:
                            st.error("❌ Configuration Failed")
                            st.code(push_res["lab_device"].result)
                        else:
                            st.success("✅ Applied Successfully!")
                            with st.expander("Show Device Output"):
                                st.code(push_res["lab_device"].result)
                                
                    except Exception as e:
                        st.error(f"Connection Error: {e}")

    with col2:
        if st.button("Back"):
            st.session_state['step'] = 1
            st.rerun()

else:
    st.info("👈 Please fill in the details in the sidebar to start.")

