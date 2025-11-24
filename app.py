import streamlit as st
import yaml
import logging
import os
from jinja2 import Environment, FileSystemLoader, meta, nodes
from nornir import InitNornir
from nornir_scrapli.tasks import send_configs
from nornir_jinja2.plugins.tasks import template_file

# --- CONFIGURATION ---
# Suppress Nornir logs in the console to keep it clean
logging.getLogger("nornir").setLevel(logging.ERROR)
st.set_page_config(page_title="Config Tool", layout="wide")
st.title("Config Tool")

# --- SESSION STATE MANAGEMENT ---
# Initialize session variables to persist data between re-runs
if 'generated_config' not in st.session_state:
    st.session_state['generated_config'] = ""
if 'step' not in st.session_state:
    st.session_state['step'] = 1  # 1 = Input, 2 = Review/Push

# --- AST PARSER (Extracts variables & defaults from Jinja2 templates) ---
def get_template_vars_with_defaults(platform_dir, template_name):
    """
    Parses the Jinja2 template using AST (Abstract Syntax Tree).
    Returns a dictionary of variables and their default values (if any).
    Example: {{ hostname | default('Router1') }} -> {'hostname': 'Router1'}
    """
    env = Environment(loader=FileSystemLoader("templates"))
    try:
        # Load template source code
        template_source = env.loader.get_source(env, f"{platform_dir}/{template_name}")[0]
        ast = env.parse(template_source)
        
        # Find all undeclared variables
        all_vars = meta.find_undeclared_variables(ast)
        # Remove 'host' as it is injected by Nornir automatically
        if 'host' in all_vars:
            all_vars.remove('host')
            
        vars_map = {v: "" for v in all_vars}

        # Recursive function to walk through the AST and find 'default' filters
        def walk_node(node):
            if isinstance(node, nodes.Filter) and node.name == 'default':
                if isinstance(node.node, nodes.Name):
                    var_name = node.node.name
                    # Check if the default value is a constant (string/int)
                    if node.args and isinstance(node.args[0], nodes.Const):
                        if var_name in vars_map:
                            vars_map[var_name] = node.args[0].value
            for child in node.iter_child_nodes():
                walk_node(child)

        walk_node(ast)
        return vars_map
    except Exception as e:
        # Return empty dict on parsing error
        return {}

# --- INVENTORY GENERATOR ---
def create_inventory_file(ip, driver_platform, username, password):
    """
    Generates a temporary 'hosts.yaml' file for Nornir.
    Includes specific Scrapli options for GNS3/Legacy device support.
    """
    inventory_data = {
        "lab_device": {
            "hostname": ip,
            "platform": driver_platform,
            "username": username,
            "password": password,
            "port": 22,
            "connection_options": {
                "scrapli": {
                    # Increased timeouts for slow virtual devices (GNS3/EVE-NG)
                    "timeout_socket": 10,
                    "timeout_transport": 30,
                    "timeout_ops": 60,
                    "extras": {
                        "auth_strict_key": False,
                        "transport_options": {
                            "open_cmd": [
                                # Legacy Crypto Algorithms (Required for old Cisco IOS / FortiGate 6.x)
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

# --- SIDEBAR UI ---
with st.sidebar:
    st.header("1. Device Connection")
    target_ip = st.text_input("IP Address", value="192.168.122.100")
    
    st.header("2. Authentication")
    username = st.text_input("Username", value="admin")
    password = st.text_input("Password", type="password")
    
    st.divider()

    st.header("3. Platform & Template")
    
    # List of folder names in your 'templates/' directory
    folder_options = ["ios", "nxos", "arubaos", "arubaos-cx", "fortios"]
    selected_platform_folder = st.selectbox("Platform Family", folder_options)
    
    # --- DRIVER MAPPING LOGIC ---
    # Maps the user-friendly folder name to the actual Scrapli driver name
    if selected_platform_folder == "ios":
        driver_platform = "cisco_iosxe"    # Scrapli standard for IOS/IOS-XE
    elif selected_platform_folder == "nxos":
        driver_platform = "cisco_nxos"     # Scrapli standard
    elif selected_platform_folder == "arubaos-cx":
        driver_platform = "aruba_aoscx"    # Scrapli standard
    elif selected_platform_folder == "arubaos":
        driver_platform = "aruba_aoss"     # Community driver (Provision)
    elif selected_platform_folder == "fortios":
        driver_platform = "fortinet_fortios" # Community driver
    else:
        driver_platform = selected_platform_folder # Fallback

    # Scan templates directory
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
        # Extract variables from the selected template
        vars_map = get_template_vars_with_defaults(selected_platform_folder, selected_template)
        
        if not vars_map:
            st.caption("No variables in this template.")
        else:
            for var_name, default_val in vars_map.items():
                # Format label (e.g., ntp_server -> Ntp Server)
                label = var_name.replace("_", " ").title()
                val = st.text_input(
                    label, 
                    value=str(default_val), 
                    key=f"dyn_{var_name}"
                )
                dynamic_inputs[var_name] = val
    
    st.divider()

    # GENERATE BUTTON
    if st.button("Generate Config 🎲", type="primary"):
        if not target_ip:
            st.warning("Please enter IP Address first!")
        else:
            # Create inventory
            create_inventory_file(target_ip, driver_platform, username, password)
            try:
                # Initialize Nornir
                nr = InitNornir(
                    runner={"plugin": "threaded", "options": {"num_workers": 1}},
                    inventory={"plugin": "SimpleInventory", "options": {"host_file": "hosts.yaml"}}
                )
                
                # Render Template
                res = nr.run(
                    task=template_file,
                    template=f"{selected_platform_folder}/{selected_template}",
                    path="templates",
                    **dynamic_inputs # Pass dynamic inputs to Jinja2
                )
                
                if res["lab_device"].failed:
                    st.error(f"Render Failed: {res['lab_device'].result}")
                else:
                    st.session_state['generated_config'] = res["lab_device"].result
                    st.session_state['step'] = 2
                    
            except Exception as e:
                st.error(f"Critical Error: {e}")

# --- MAIN WINDOW (REVIEW & PUSH) ---

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
                    # Update inventory (in case password changed)
                    create_inventory_file(target_ip, driver_platform, username, password)
                    
                    try:
                        nr_push = InitNornir(
                            runner={"plugin": "threaded", "options": {"num_workers": 1}},
                            inventory={"plugin": "SimpleInventory", "options": {"host_file": "hosts.yaml"}}
                        )
                        
                        # Send commands
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
            st.rerun() # Reruns the script to reset the view

else:
    # Welcome Screen
    st.info("👈 Please fill in the details in the sidebar to start.")

