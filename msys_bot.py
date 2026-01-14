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

sys.stdout.reconfigure(encoding='utf-8')

# Headers simulando navegador real
HEADERS_PADRAO = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
    "Content-Type": "application/json"
}

def print_log(msg):
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
        print_log("✓ Token salvo no Supabase.")
    except Exception as e:
        print_log(f"❌ Erro ao salvar token: {e}")

# --- NOVA LÓGICA DE SESSÃO ---
# Criamos uma sessão global para manter cookies e conexão viva
session = requests.Session()
session.headers.update(HEADERS_PADRAO)

def realizar_login_sessao(refresh_token):
    """Faz login e atualiza a sessão com o novo token"""
    url = f"{BASE_URL}/api/openapi/v1/login"
    try:
        # Usa a sessão para manter cookies
        response = session.post(url, params={"refresh-token": refresh_token}, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        access = data.get("accesstoken")
        new_refresh = data.get("refreshtoken")
        
        # Atualiza o header da sessão para as próximas chamadas
        session.headers.update({"Authorization": f"Bearer {access}"})
        
        return access, new_refresh
    except Exception as e:
        print_log(f"Erro login MSYS: {e}")
        return None, None

def renovar_autenticacao_completa():
    print_log("🔄 TENTATIVA DE RENOVAÇÃO DE EMERGÊNCIA...")
    
    # Pequena pausa para o servidor respirar
    time.sleep(5)
    
    creds = carregar_credentials()
    if not creds: return None
    
    access, new_refresh = realizar_login_sessao(creds['refresh_token'])
    if access and new_refresh:
        salvar_credentials({'refresh_token': new_refresh})
        print_log("✓ Autenticação recuperada e Sessão atualizada!")
        return access
    
    print_log("❌ A renovação falhou. Token inválido.")
    return None

def buscar_data_individual(idt_person):
    """Busca detalhes usando a sessão global"""
    url = f"{BASE_URL}/api/openapi/v1/person/findForEdit"
    try:
        response = session.get(url, params={"code": idt_person}, timeout=20)
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
        time.sleep(0.2)
        resp = requests.post(WEBHOOK_URL, json=payload, headers=headers, timeout=10)
        if resp.status_code in [200, 201]:
            print_log(f"   🎉 ENVIADO: {pessoa['nome']}")
    except Exception as e:
        print_log(f"   ❌ Erro Webhook: {e}")

def processar_lote_pessoas(lote_pessoas, dia_hoje, mes_hoje):
    candidatos_detalhe = []
    
    # 1. Filtro Rápido
    for p in lote_pessoas:
        data_lista = p.get("dtaBirth")
        if data_lista:
            if verificar_data_match(data_lista, dia_hoje, mes_hoje):
                enviar_webhook(formatar_pessoa(p, data_lista))
        else:
            if p.get("idtPerson"):
                candidatos_detalhe.append(p)
    
    # 2. Busca Detalhada
    if candidatos_detalhe:
        # IMPORTANTE: Em sessão persistente, não podemos usar threads demais
        # pois elas compartilham o mesmo socket. Reduzido para 3.
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_p = {
                executor.submit(buscar_data_individual, p["idtPerson"]): p 
                for p in candidatos_detalhe
            }
            for future in as_completed(future_to_p):
                p = future_to_p[future]
                dta_detalhe = future.result()
                if dta_detalhe and verificar_data_match(dta_detalhe, dia_hoje, mes_hoje):
                    enviar_webhook(formatar_pessoa(p, dta_detalhe))

def executar_varredura_stream():
    url = f"{BASE_URL}/api/openapi/v1/person"
    
    first = 0
    page_size_real = 100
    
    tz_br = timezone(timedelta(hours=-3))
    hoje = datetime.now(tz_br)
    dia_hoje = hoje.day
    mes_hoje = hoje.month
    
    print_log(f"🚀 Iniciando Varredura com SESSÃO (Data: {dia_hoje}/{mes_hoje})")

    while True:
        payload = {"pageSize": page_size_real, "first": first}
        sucesso_pagina = False
        
        time.sleep(2) # Pausa entre páginas

        for tentativa in range(3):
            try:
                # Usa a sessão global
                response = session.post(url, json=payload, timeout=45)
                response.raise_for_status()
                
                data = response.json()
                items = data.get("items", [])
                
                if not items:
                    print_log(f"🏁 Fim da lista no índice {first}.")
                    return
                
                qtd_recebida = len(items)
                print_log(f"📦 Lote {first} a {first+qtd_recebida} baixado...")
                
                processar_lote_pessoas(items, dia_hoje, mes_hoje)

                first += qtd_recebida
                sucesso_pagina = True
                break 
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 401:
                    print_log(f"⚠️ Sessão expirou na pág {first}. Renovando...")
                    # Se renovar, a sessão global é atualizada automaticamente
                    novo_access = renovar_autenticacao_completa()
                    if novo_access:
                        continue
                    else:
                        print_log("❌ FIM: Falha na renovação.")
                        return
                print_log(f"⚠️ Erro HTTP na página {first}: {e}")
                time.sleep(5)
            except Exception as e:
                print_log(f"⚠️ Erro Conexão na página {first}: {e}")
                time.sleep(5)
        
        if not sucesso_pagina:
            print_log(f"❌ PÁGINA {first} FALHOU 3x. Pulando...")
            first += page_size_real

def main():
    print_log("=== INICIANDO ROBÔ (SESSÃO PERSISTENTE) ===")
    creds = carregar_credentials()
    if not creds: return
    
    time.sleep(1)
    
    # Login inicial
    access, new_refresh = realizar_login_sessao(creds['refresh_token'])
    if not access: 
        print_log("❌ Falha no login inicial.")
        return
    
    salvar_credentials({'refresh_token': new_refresh})
    
    executar_varredura_stream()
    
    print_log("=== CONCLUÍDO ===")

def modo_manutencao_renovar_token():
    print_log("=== MODO MANUTENÇÃO ===")
    creds = carregar_credentials()
    if not creds: return
    access, new_refresh = realizar_login_sessao(creds['refresh_token'])
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
