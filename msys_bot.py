import json
import os
import time
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
        print("✓ Token salvo no Supabase.")
    except Exception as e:
        print(f"❌ Erro ao salvar token: {e}")

def obter_access_token(refresh_token):
    url = f"{BASE_URL}/api/openapi/v1/login"
    try:
        response = requests.post(url, params={"refresh-token": refresh_token}, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data.get("accesstoken"), data.get("refreshtoken")
    except Exception as e:
        print(f"Erro login: {e}")
        return None, None

def buscar_pessoas_correto(access_token):
    """
    Busca SEQUENCIALMENTE respeitando o limite da API de 10 em 10.
    Não pula registros e trata erros de página.
    """
    url = f"{BASE_URL}/api/openapi/v1/person"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    todas_pessoas = []
    first = 0
    # A API força 10, então vamos pedir 10 para não confundir a lógica
    page_size_real = 10 
    
    print(f"Iniciando varredura completa (Lotes de {page_size_real})...")
    
    while True:
        payload = {
            "pageSize": page_size_real,
            "first": first
        }
        
        sucesso_pagina = False
        
        # Tentativa com Retry
        for tentativa in range(3):
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=30)
                
                # Se a API devolver erro 500/400, lança exceção
                response.raise_for_status()
                
                data = response.json()
                items = data.get("items", [])
                
                # Se a lista vier vazia, acabou o banco de dados
                if not items:
                    print(f"✓ Fim da lista atingido no índice {first}.")
                    return todas_pessoas
                
                todas_pessoas.extend(items)
                qtd_recebida = len(items)
                
                # Log a cada 500 pessoas para não poluir
                if len(todas_pessoas) % 500 == 0:
                    print(f"   -> Baixados: {len(todas_pessoas)} pessoas...")

                # CORREÇÃO CRÍTICA:
                # Incrementa o 'first' exatamente com o número de itens que vieram
                first += qtd_recebida
                
                sucesso_pagina = True
                break # Sucesso, sai do loop de tentativas
                
            except Exception as e:
                print(f"⚠️ Erro no lote {first} (Tentativa {tentativa+1}): {e}")
                time.sleep(2) # Espera um pouco
        
        if not sucesso_pagina:
            print(f"❌ PÁGINA {first} IGNORADA APÓS ERROS. Pulando para o próximo lote...")
            # Se deu erro fatal nesse lote, pula ele na marra para não travar o script
            first += page_size_real
            
    return todas_pessoas

def buscar_data_individual(access_token, idt_person):
    """Busca detalhes de uma pessoa"""
    url = f"{BASE_URL}/api/openapi/v1/person/findForEdit"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        response = requests.get(url, params={"code": idt_person}, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            # Tenta achar a data em todos os cantos possíveis
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
    """Verifica se a data bate com o dia/mês alvo"""
    try:
        if not data_raw: return False
        
        dt = None
        if isinstance(data_raw, (int, float)):
            # Timestamp em milissegundos
            dt = datetime.fromtimestamp(data_raw / 1000)
        else:
            # String ISO ou Data normal
            str_data = str(data_raw).split("T")[0] # Pega só YYYY-MM-DD
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
        print(f"   Ignorado (sem telefone): {pessoa['nome']}")
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
    
    # 1. Filtro Rápido (quem já tem data na lista)
    for p in pessoas:
        data_lista = p.get("dtaBirth")
        if data_lista:
            # Se tem data, confere já
            if verificar_data_match(data_lista, dia_hoje, mes_hoje):
                confirmados.append(formatar_pessoa(p, data_lista))
        else:
            # Se não tem data, joga pra fila de busca detalhada
            if p.get("idtPerson"):
                candidatos_para_detalhe.append(p)
                
    print(f"   - Confirmados via lista rápida: {len(confirmados)}")
    print(f"   - Sem data (buscar detalhes): {len(candidatos_para_detalhe)}")
    
    # 2. Busca Detalhada em Paralelo
    if candidatos_para_detalhe:
        print("   -> Buscando detalhes em paralelo...")
        with ThreadPoolExecutor(max_workers=12) as executor:
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
    print("=== INICIANDO ROBÔ CORRIGIDO ===")
    
    creds = carregar_credentials()
    if not creds: return
    
    access, new_refresh = obter_access_token(creds['refresh_token'])
    if not access: return
    
    salvar_credentials({'refresh_token': new_refresh})
    
    # 1. Baixar TUDO (sem pular ninguém)
    todas_pessoas = buscar_pessoas_correto(access)
    print(f"\nBase total baixada: {len(todas_pessoas)} pessoas.")
    
    if len(todas_pessoas) < 100:
        print("⚠️ ALERTA: A lista parece muito pequena. Verifique se o token tem permissão total.")
        
    # 2. Filtrar e Enviar
    processar_e_enviar(todas_pessoas, access)
    
    print("\n=== CONCLUÍDO ===")

if __name__ == "__main__":
    main()
