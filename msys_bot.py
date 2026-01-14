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

def get_supabase_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def carregar_credentials():
    """Lê o refresh token do Supabase"""
    try:
        supabase = get_supabase_client()
        response = supabase.table("credentials").select("*").limit(1).execute()
        if response.data and len(response.data) > 0:
            return {"refresh_token": response.data[0].get("refresh_token")}
        print("⚠️  Nenhum refresh_token encontrado no Supabase!")
        return None
    except Exception as e:
        print(f"❌ Erro Supabase: {e}")
        return None

def salvar_credentials(credentials):
    """Salva o novo refresh token no Supabase"""
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
        print("✓ Token renovado salvo no Supabase.")
    except Exception as e:
        print(f"❌ Erro ao salvar token: {e}")

def obter_access_token(refresh_token):
    """Pede um novo access token para a API da MSYS"""
    url = f"{BASE_URL}/api/openapi/v1/login"
    try:
        response = requests.post(url, params={"refresh-token": refresh_token}, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data.get("accesstoken"), data.get("refreshtoken")
    except Exception as e:
        print(f"Erro login MSYS: {e}")
        return None, None

def renovar_autenticacao_completa():
    """
    Função de emergência: Vai no Supabase, pega o refresh token atual,
    renova na MSYS e salva o novo. Retorna o novo access_token.
    """
    print("\n🔄 RENOVANDO TOKEN VENCIDO NO MEIO DO PROCESSO...")
    creds = carregar_credentials()
    if not creds: return None
    
    access, new_refresh = obter_access_token(creds['refresh_token'])
    if access and new_refresh:
        salvar_credentials({'refresh_token': new_refresh})
        print("✓ Autenticação renovada com sucesso! Retomando...")
        return access
    
    print("❌ Falha crítica ao renovar token.")
    return None

def buscar_pessoas_blindado(access_token_inicial):
    """
    Busca SEQUENCIALMENTE respeitando a API.
    Se der erro 401, renova o token e continua.
    Lê a quantidade exata retornada para não pular ninguém.
    """
    url = f"{BASE_URL}/api/openapi/v1/person"
    
    access_token_atual = access_token_inicial
    
    headers = {
        "Authorization": f"Bearer {access_token_atual}",
        "Content-Type": "application/json"
    }
    
    todas_pessoas = []
    first = 0
    page_size_real = 100 
    
    print(f"Iniciando varredura (Pedindo lotes de {page_size_real})...")
    
    while True:
        payload = {
            "pageSize": page_size_real,
            "first": first
        }
        
        sucesso_pagina = False
        
        # Loop de tentativas (Retry)
        for tentativa in range(3):
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=45)
                response.raise_for_status()
                
                data = response.json()
                items = data.get("items", [])
                
                if not items:
                    print(f"✓ Fim da lista atingido no índice {first}.")
                    return todas_pessoas
                
                todas_pessoas.extend(items)
                qtd_recebida = len(items)
                
                # Log de progresso a cada 1000
                if len(todas_pessoas) % 1000 < qtd_recebida: 
                    print(f"   -> Baixados: {len(todas_pessoas)} pessoas...")

                # ATENÇÃO: Soma exatamente o que veio para não pular ninguém
                first += qtd_recebida
                sucesso_pagina = True
                break 
                
            except requests.exceptions.HTTPError as e:
                # SE O ERRO FOR 401 (TOKEN VENCIDO)
                if e.response.status_code == 401:
                    print(f"⚠️ Token Venceu na página {first}. Tentando renovar...")
                    novo_access = renovar_autenticacao_completa()
                    if novo_access:
                        access_token_atual = novo_access
                        headers["Authorization"] = f"Bearer {access_token_atual}"
                        continue # Tenta a mesma página de novo
                    else:
                        print("❌ Não foi possível renovar. Abortando busca.")
                        return todas_pessoas
                
                print(f"⚠️ Erro genérico no lote {first} (Tentativa {tentativa+1}): {e}")
                time.sleep(5)
            except Exception as e:
                print(f"⚠️ Erro de conexão no lote {first}: {e}")
                time.sleep(5)
        
        if not sucesso_pagina:
            print(f"❌ PÁGINA {first} IGNORADA APÓS FALHAS. Pulando este lote...")
            first += page_size_real
            
    return todas_pessoas

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
            print(f"   ✓ ENVIADO: {pessoa['nome']}")
        else:
            print(f"   ❌ Erro envio: {resp.text}")
    except Exception as e:
        print(f"   ❌ Erro conexão: {e}")

def processar_e_enviar(pessoas, access_token):
    # Data de Hoje (Brasília)
    tz_br = timezone(timedelta(hours=-3))
    hoje = datetime.now(tz_br)
    dia_hoje = hoje.day
    mes_hoje = hoje.month
    
    print(f"\n🎂 Buscando aniversariantes de: {dia_hoje}/{mes_hoje}")
    
    candidatos_para_detalhe = []
    confirmados = []
    
    # 1. Filtro Rápido (para quem já tem data na listagem)
    for p in pessoas:
        data_lista = p.get("dtaBirth")
        if data_lista:
            if verificar_data_match(data_lista, dia_hoje, mes_hoje):
                confirmados.append(formatar_pessoa(p, data_lista))
        else:
            if p.get("idtPerson"):
                candidatos_para_detalhe.append(p)
                
    print(f"   - Confirmados via lista rápida: {len(confirmados)}")
    print(f"   - Sem data (buscar detalhes): {len(candidatos_para_detalhe)}")
    
    # 2. Busca Detalhada em Paralelo
    if candidatos_para_detalhe:
        print("   -> Buscando detalhes em paralelo...")
        # Usa 10 threads para não sobrecarregar
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_p = {
                executor.submit(buscar_data_individual, access_token, p["idtPerson"]): p 
                for p in candidatos_para_detalhe
            }
            
            count = 0
            total = len(candidatos_para_detalhe)
            for future in as_completed(future_to_p):
                p = future_to_p[future]
                count += 1
                if count % 500 == 0: print(f"      Progresso: {count}/{total}")
                
                dta_detalhe = future.result()
                if dta_detalhe and verificar_data_match(dta_detalhe, dia_hoje, mes_hoje):
                    confirmados.append(formatar_pessoa(p, dta_detalhe))

    print(f"\n🎉 Total Final de Aniversariantes: {len(confirmados)}")
    for c in confirmados:
        enviar_webhook(c)

def main():
    print("=== INICIANDO ROBÔ DE ANIVERSÁRIOS ===")
    
    creds = carregar_credentials()
    if not creds: return
    
    access, new_refresh = obter_access_token(creds['refresh_token'])
    if not access: return
    
    # Salva o novo token imediatamente
    salvar_credentials({'refresh_token': new_refresh})
    
    # 1. Baixar TUDO (com proteção contra token vencido)
    todas_pessoas = buscar_pessoas_blindado(access)
    print(f"\nBase total baixada: {len(todas_pessoas)} pessoas.")
    
    # 2. Filtrar e Enviar
    processar_e_enviar(todas_pessoas, access)
    
    print("\n=== CONCLUÍDO ===")

def modo_manutencao_renovar_token():
    """Função leve apenas para manter o token vivo no Supabase (usada pelo cron de 2h)"""
    print("=== MODO MANUTENÇÃO: RENOVAÇÃO DE TOKEN ===")
    creds = carregar_credentials()
    if not creds: return
    
    # Tenta renovar
    access, new_refresh = obter_access_token(creds['refresh_token'])
    
    if access and new_refresh:
        salvar_credentials({'refresh_token': new_refresh})
        print("✓ Sucesso: Token renovado e salvo no Supabase.")
    else:
        print("❌ Falha: Não foi possível renovar o token.")

if __name__ == "__main__":
    # Verifica argumentos do sistema para saber qual modo rodar
    if len(sys.argv) > 1 and sys.argv[1] == "--renovar":
        modo_manutencao_renovar_token()
    else:
        main()
