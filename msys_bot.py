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

# Configuração de Logs
sys.stdout.reconfigure(encoding='utf-8')

# Headers (Máscara de Navegador)
HEADERS_PADRAO = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Connection": "keep-alive"
}

# SESSÃO GLOBAL
session = requests.Session()
session.headers.update(HEADERS_PADRAO)

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
    except Exception as e:
        print_log(f"❌ Erro ao salvar token: {e}")

def obter_access_token(refresh_token):
    url = f"{BASE_URL}/api/openapi/v1/login"
    try:
        response = session.post(url, params={"refresh-token": refresh_token}, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        ac = data.get("accesstoken")
        ref = data.get("refreshtoken")
        
        if ac:
            session.headers.update({"Authorization": f"Bearer {ac}"})
            
        return ac, ref
    except Exception as e:
        print_log(f"Erro login MSYS: {e}")
        return None, None

def renovar_autenticacao_completa():
    print_log("🔄 RENOVAÇÃO DE TOKEN ACIONADA...")
    creds = carregar_credentials()
    if not creds: return None
    
    time.sleep(2)
    
    access, new_refresh = obter_access_token(creds['refresh_token'])
    if access and new_refresh:
        salvar_credentials({'refresh_token': new_refresh})
        print_log("✓ Autenticação renovada e Sessão atualizada!")
        return access
    
    print_log("❌ Falha crítica ao renovar token.")
    return None

def buscar_pessoas_bruto(access_token_inicial):
    """
    Busca TUDO (SEM FILTRO NA API).
    """
    url = f"{BASE_URL}/api/openapi/v1/person"
    session.headers.update({"Authorization": f"Bearer {access_token_inicial}"})
    
    todas_pessoas = []
    first = 0
    page_size_real = 100
    
    print_log(f"📥 Baixando BASE COMPLETA (Sem filtros na API)...")
    
    while True:
        payload = {
            "pageSize": page_size_real,
            "first": first
        }
        
        sucesso_pagina = False
        
        for tentativa in range(3):
            try:
                response = session.post(url, json=payload, timeout=45)
                response.raise_for_status()
                
                data = response.json()
                items = data.get("items", [])
                
                if not items:
                    print_log(f"✓ Fim da lista atingido no índice {first}.")
                    return todas_pessoas
                
                todas_pessoas.extend(items)
                qtd_recebida = len(items)
                
                if len(todas_pessoas) % 2000 < qtd_recebida: 
                    print_log(f"   -> Baixados: {len(todas_pessoas)} pessoas...")

                first += qtd_recebida
                sucesso_pagina = True
                break 
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 401:
                    print_log(f"⚠️ Token expirou na pág {first}. Renovando...")
                    novo_access = renovar_autenticacao_completa()
                    if novo_access:
                        continue 
                    else:
                        print_log("❌ Não foi possível renovar. Abortando busca.")
                        return todas_pessoas
                print_log(f"⚠️ Erro HTTP na página {first}: {e}")
                time.sleep(2)
            except Exception as e:
                print_log(f"⚠️ Erro de conexão no lote {first}: {e}")
                time.sleep(2)
        
        if not sucesso_pagina:
            print_log(f"🛑 PÁGINA {first} FALHOU 3x. Encerrando download.")
            break
            
    return todas_pessoas

def buscar_data_individual(idt_person):
    """Busca detalhes para pegar a data escondida"""
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

def extrair_lista_telefones(p_dict):
    """Retorna uma LISTA de telefones únicos formatados"""
    lista_telefones = set() 
    
    contact = p_dict.get("contactVOs")
    if isinstance(contact, dict):
        phones = contact.get("phoneVOs", [])
        
        for phone in phones:
            ddd = phone.get('dddPhone', '')
            num = phone.get('numPhone', '')
            
            if ddd and num:
                ddd_limpo = "".join(filter(str.isdigit, str(ddd)))
                num_limpo = "".join(filter(str.isdigit, str(num)))
                full_num = f"55{ddd_limpo}{num_limpo}"
                if len(full_num) >= 12: 
                    lista_telefones.add(full_num)
    
    return list(lista_telefones)

def enviar_webhook(nome, telefone, data_raw):
    try:
        payload = {
            "nome": nome,
            "telefone": telefone,
            "data_nascimento": str(data_raw)
        }
        headers = {"apikey": API_KEY_BOTCONVERSA}
        resp = requests.post(WEBHOOK_URL, json=payload, headers=headers, timeout=10)
        if resp.status_code in [200, 201]:
            print_log(f"   ✓ ENVIADO: {nome} -> {telefone}")
        else:
            print_log(f"   ❌ Erro envio ({telefone}): {resp.text}")
    except Exception as e:
        print_log(f"   ❌ Erro conexão: {e}")

def processar_e_enviar(pessoas):
    tz_br = timezone(timedelta(hours=-3))
    hoje = datetime.now(tz_br)
    dia_hoje = hoje.day
    mes_hoje = hoje.month
    
    print_log(f"\n🎂 INICIANDO FILTRAGEM LOCAL DE: {dia_hoje}/{mes_hoje}")
    print_log(f"   Total de registros brutos: {len(pessoas)}")
    
    # --- FILTRAGEM: ATIVOS E SEM FIADORES ---
    pessoas_filtradas = []
    ignorado_inativo = 0
    ignorado_fiador = 0
    
    for p in pessoas:
        status = p.get("indStatus")
        
        # Pega os tipos (convertendo para string maiúscula para garantir)
        tipo_ind = str(p.get("indType", "")).upper()
        tipo_first = str(p.get("firstType", "")).upper()
        tipo_sep = str(p.get("typesSeparate", "")).upper()
        
        # Verifica se é fiador em qualquer campo
        eh_fiador = "GU" in tipo_ind or "GUARANTOR" in tipo_first or "FIADOR" in tipo_sep
        
        if status != "A":
            ignorado_inativo += 1
            continue
            
        if eh_fiador:
            ignorado_fiador += 1
            continue
            
        # Se passou pelos filtros, adiciona
        pessoas_filtradas.append(p)
            
    print_log(f"   ✅ Ativos (Clientes/Proprietários): {len(pessoas_filtradas)}")
    print_log(f"   🗑️ Inativos ignorados: {ignorado_inativo}")
    print_log(f"   🚫 Fiadores ignorados: {ignorado_fiador}")
    
    candidatos_para_detalhe = []
    aniversariantes_confirmados = []
    
    # 2. Filtro Rápido (em cima da lista limpa)
    for p in pessoas_filtradas:
        data_lista = p.get("dtaBirth")
        if data_lista:
            if verificar_data_match(data_lista, dia_hoje, mes_hoje):
                aniversariantes_confirmados.append((p, data_lista))
        else:
            if p.get("idtPerson"):
                candidatos_para_detalhe.append(p)
                
    print_log(f"   - Confirmados (dados rápidos): {len(aniversariantes_confirmados)}")
    print_log(f"   - Precisam de busca detalhada: {len(candidatos_para_detalhe)}")
    
    # 3. Busca Detalhada
    if candidatos_para_detalhe:
        print_log("   -> Buscando detalhes em paralelo...")
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_p = {
                executor.submit(buscar_data_individual, p["idtPerson"]): p 
                for p in candidatos_para_detalhe
            }
            
            count = 0
            total = len(candidatos_para_detalhe)
            for future in as_completed(future_to_p):
                p = future_to_p[future]
                count += 1
                if count % 1000 == 0: print_log(f"      Progresso: {count}/{total}")
                
                dta_detalhe = future.result()
                if dta_detalhe and verificar_data_match(dta_detalhe, dia_hoje, mes_hoje):
                    aniversariantes_confirmados.append((p, dta_detalhe))

    print_log(f"\n🎉 Total Final de Aniversariantes VÁLIDOS: {len(aniversariantes_confirmados)}")
    
    # --- ENVIO MÚLTIPLO ---
    for item in aniversariantes_confirmados:
        pessoa_dict = item[0]
        data_aniv = item[1]
        nome = pessoa_dict.get("namPerson", "Cliente")
        
        telefones = extrair_lista_telefones(pessoa_dict)
        
        if not telefones:
            print_log(f"   ⚠️ Ignorado (sem telefone válido): {nome}")
            continue
            
        if len(telefones) > 1:
            print_log(f"   ℹ️ {nome} possui {len(telefones)} telefones. Enviando para todos.")
            
        for tel in telefones:
            enviar_webhook(nome, tel, data_aniv)

def main():
    print_log("=== INICIANDO ROBÔ (SEM FIADORES + MULTI-PHONE) ===")
    
    creds = carregar_credentials()
    if not creds: return
    
    access, new_refresh = obter_access_token(creds['refresh_token'])
    if not access: return
    
    salvar_credentials({'refresh_token': new_refresh})
    
    # 1. Baixar TUDO (26k)
    todas_pessoas = buscar_pessoas_bruto(access)
    print_log(f"\nDownload concluído: {len(todas_pessoas)} registros.")
    
    # 2. Filtrar e Enviar
    processar_e_enviar(todas_pessoas)
    
    print_log("\n=== CONCLUÍDO ===")

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
