import json
import os
import time
import sys
import requests
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from supabase import create_client, Client

# --- CONFIGURAÇÕES ---
BASE_URL = "https://www.msysimob.com.br/msys-imob-web"
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://new-backend.botconversa.com.br/api/v1/webhooks-automation/catch/147503/g8en0hO6l4RJ/")
API_KEY_BOTCONVERSA = os.getenv("API_KEY_BOTCONVERSA", "a33c54d2-5f92-4f29-b78d-5082b7b70518")

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://rzkskovdlaktqidqeamp.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJ6a3Nrb3ZkbGFrdHFpZHFlYW1wIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2ODA4MzE3NCwiZXhwIjoyMDgzNjU5MTc0fQ.DJlNkDbT-0rYDm0RttPp-fe4lXMJFNFNfCxHe_xkCqo")

# Configuração de Logs imediatos
sys.stdout.reconfigure(encoding='utf-8')

def print_log(msg):
    """Força o print a aparecer imediatamente no GitHub Actions"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def get_supabase_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def carregar_credentials():
    try:
        supabase = get_supabase_client()
        response = supabase.table("credentials").select("*").limit(1).execute()
        if response.data and len(response.data) > 0:
            return {"refresh_token": response.data[0].get("refresh_token")}
        print_log("⚠️  Nenhum refresh_token encontrado no Supabase!")
        return None
    except Exception as e:
        print_log(f"❌ Erro Supabase: {e}")
        return None

def salvar_credentials(credentials):
    try:
        novo_token = credentials.get("refresh_token")
        supabase = get_supabase_client()
        response = supabase.table("credentials").select("id").limit(1).execute()
        
        if response.data:
            rec_id = response.data[0]["id"]
            supabase.table("credentials").update({
                "refresh_token": novo_token,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("id", rec_id).execute()
        else:
            supabase.table("credentials").insert({
                "refresh_token": novo_token,
                "updated_at": datetime.utcnow().isoformat()
            }).execute()
        print_log("✓ Token renovado salvo no Supabase.")
    except Exception as e:
        print_log(f"❌ Erro ao salvar token: {e}")

def obter_access_token(refresh_token):
    url = f"{BASE_URL}/api/openapi/v1/login"
    try:
        response = requests.post(url, params={"refresh-token": refresh_token}, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data.get("accesstoken"), data.get("refreshtoken")
    except Exception as e:
        print_log(f"Erro login MSYS: {e}")
        return None, None

def renovar_autenticacao_completa():
    print_log("🔄 RENOVANDO TOKEN VENCIDO NO MEIO DO PROCESSO...")
    creds = carregar_credentials()
    if not creds: return None
    access, new_refresh = obter_access_token(creds['refresh_token'])
    if access and new_refresh:
        salvar_credentials({'refresh_token': new_refresh})
        print_log("✓ Autenticação renovada! Retomando...")
        return access
    print_log("❌ Falha crítica ao renovar token.")
    return None

def buscar_data_individual(access_token, idt_person):
    """Busca detalhes de uma pessoa"""
    url = f"{BASE_URL}/api/openapi/v1/person/findForEdit"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        response = requests.get(url, params={"code": idt_person}, headers=headers, timeout=20)
        if response.status_code == 200:
            data = response.json()
            locais = [
                data.get("personIndividualForm", {}).get("birth"),
                data.get("personIndividual", {}).get("birth"),
                data.get("dtaBirth")
            ]
            for data_raw in locais:
                if data_raw: return data_raw
    except:
        pass
    return None

def verificar_data_match(data_raw, dia_alvo, mes_alvo):
    try:
        if not data_raw: return False
        dt = None
        if isinstance(data_raw, (int, float)):
            dt = datetime.fromtimestamp(data_raw / 1000)
        else:
            str_data = str(data_raw).split("T")[0]
            if "-" in str_data:
                dt = datetime.strptime(str_data, "%Y-%m-%d")
        if dt:
            return dt.day == dia_alvo and dt.month == mes_alvo
    except:
        return False
    return False

def formatar_pessoa(p_dict, data_raw):
    tel = ""
    contact = p_dict.get("contactVOs")
    if isinstance(contact, dict):
        phones = contact.get("phoneVOs", [])
        if phones and len(phones) > 0:
            ddd = phones[0].get('dddPhone','')
            num = phones[0].get('numPhone','')
            tel = f"55{ddd}{num}"
    
    return {
        "nome": p_dict.get("namPerson"),
        "telefone": tel,
        "data_raw": data_raw
    }

def enviar_webhook(pessoa):
    if not pessoa['telefone'] or len(pessoa['telefone']) < 10:
        return

    try:
        payload = {
            "nome": pessoa['nome'],
            "telefone": pessoa['telefone'],
            "data_nascimento": str(pessoa['data_raw'])
        }
        headers = {"apikey": API_KEY_BOTCONVERSA}
        resp = requests.post(WEBHOOK_URL, json=payload, headers=headers, timeout=10)
        if resp.status_code in [200, 201]:
            print_log(f"   🎉 ENVIADO: {pessoa['nome']}")
        else:
            print_log(f"   ❌ Erro envio Webhook: {resp.text}")
    except Exception as e:
        print_log(f"   ❌ Erro conexão Webhook: {e}")

def processar_lote_pessoas(lote_pessoas, access_token, dia_hoje, mes_hoje):
    """Processa um lote de 100 pessoas imediatamente"""
    candidatos_detalhe = []
    
    # 1. Filtro Rápido (Dados que já vieram)
    for p in lote_pessoas:
        data_lista = p.get("dtaBirth")
        if data_lista:
            if verificar_data_match(data_lista, dia_hoje, mes_hoje):
                enviar_webhook(formatar_pessoa(p, data_lista))
        else:
            if p.get("idtPerson"):
                candidatos_detalhe.append(p)
    
    # 2. Busca Detalhada (se necessário)
    if candidatos_detalhe:
        # print_log(f"      🔎 Buscando detalhes de {len(candidatos_detalhe)} pessoas sem data...")
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_p = {
                executor.submit(buscar_data_individual, access_token, p["idtPerson"]): p 
                for p in candidatos_detalhe
            }
            for future in as_completed(future_to_p):
                p = future_to_p[future]
                dta_detalhe = future.result()
                if dta_detalhe and verificar_data_match(dta_detalhe, dia_hoje, mes_hoje):
                    enviar_webhook(formatar_pessoa(p, dta_detalhe))

def executar_varredura_stream(access_token_inicial):
    """Busca e processa ao mesmo tempo (Streaming)"""
    url = f"{BASE_URL}/api/openapi/v1/person"
    
    access_token_atual = access_token_inicial
    headers = {"Authorization": f"Bearer {access_token_atual}", "Content-Type": "application/json"}
    
    first = 0
    page_size_real = 100
    erros_consecutivos = 0
    total_processado = 0
    
    # Data de Hoje
    tz_br = timezone(timedelta(hours=-3))
    hoje = datetime.now(tz_br)
    dia_hoje = hoje.day
    mes_hoje = hoje.month
    
    print_log(f"🚀 Iniciando Varredura AO VIVO (Lotes de {page_size_real})")
    print_log(f"📅 Data Alvo: {dia_hoje}/{mes_hoje}")

    while True:
        payload = {"pageSize": page_size_real, "first": first}
        sucesso_pagina = False
        
        for tentativa in range(3):
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=45)
                response.raise_for_status()
                
                data = response.json()
                items = data.get("items", [])
                
                if not items:
                    print_log(f"🏁 Fim da lista atingido no índice {first}.")
                    return
                
                qtd_recebida = len(items)
                
                # --- PROCESSAMENTO IMEDIATO ---
                print_log(f"📦 Lote {first} a {first+qtd_recebida} baixado. Processando...")
                processar_lote_pessoas(items, access_token_atual, dia_hoje, mes_hoje)
                # ------------------------------

                first += qtd_recebida
                total_processado += qtd_recebida
                sucesso_pagina = True
                erros_consecutivos = 0
                break 
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 401:
                    print_log(f"⚠️ Token Venceu na página {first}. Renovando...")
                    novo_access = renovar_autenticacao_completa()
                    if novo_access:
                        access_token_atual = novo_access
                        headers["Authorization"] = f"Bearer {access_token_atual}"
                        continue
                    else:
                        print_log("❌ Falha na renovação. Abortando.")
                        return
                print_log(f"⚠️ Erro HTTP na página {first}: {e}")
                time.sleep(5)
            except Exception as e:
                print_log(f"⚠️ Erro Conexão na página {first}: {e}")
                time.sleep(5)
        
        if not sucesso_pagina:
            print_log(f"❌ PÁGINA {first} FALHOU 3x.")
            erros_consecutivos += 1
            if erros_consecutivos >= 3:
                print_log("🛑 PARADA DE EMERGÊNCIA: Muitos erros seguidos.")
                break
            first += page_size_real

def main():
    print_log("=== INICIANDO ROBÔ (MODO STREAMING) ===")
    creds = carregar_credentials()
    if not creds: return
    
    access, new_refresh = obter_access_token(creds['refresh_token'])
    if not access: return
    
    salvar_credentials({'refresh_token': new_refresh})
    
    # Executa tudo junto
    executar_varredura_stream(access)
    
    print_log("=== CONCLUÍDO COM SUCESSO ===")

def modo_manutencao_renovar_token():
    print_log("=== MODO MANUTENÇÃO ===")
    creds = carregar_credentials()
    if not creds: return
    access, new_refresh = obter_access_token(creds['refresh_token'])
    if access and new_refresh:
        salvar_credentials({'refresh_token': new_refresh})
        print_log("✓ Token renovado.")
    else:
        print_log("❌ Falha na renovação.")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--renovar":
        modo_manutencao_renovar_token()
    else:
        main()
