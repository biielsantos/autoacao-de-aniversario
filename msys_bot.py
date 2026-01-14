import json
import os
import time
import requests
import pandas as pd
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
    """Carrega o refresh_token do Supabase"""
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
    """Atualiza o refresh_token no Supabase"""
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

def buscar_pessoas_blindado(access_token, page_size=100):
    """Busca com RETRY AUTOMÁTICO para não falhar no meio das 26 mil pessoas"""
    url = f"{BASE_URL}/api/openapi/v1/person"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    todas_pessoas = []
    first = 0
    tentativas_erro_consecutivo = 0
    
    while True:
        # ATENÇÃO: Removi o filtro "indStatus": "A" para pegar TODO MUNDO (Inativos também)
        # Se quiser só ativos, descomente a linha abaixo
        payload = {
            # "indStatus": "A", 
            "pageSize": page_size,
            "first": first
        }
        
        sucesso = False
        # Tenta até 3 vezes baixar a mesma página se der erro
        for tentativa in range(3):
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=45)
                response.raise_for_status()
                data = response.json()
                items = data.get("items", [])
                
                if not items:
                    print("✓ Fim da lista encontrado.")
                    return todas_pessoas
                
                todas_pessoas.extend(items)
                print(f"✓ Baixados: {len(items)} (Total acumulado: {len(todas_pessoas)})")
                
                total_itens_api = data.get("totalItens", 0)
                if len(todas_pessoas) >= total_itens_api and total_itens_api > 0:
                    print("✓ Todos os registros foram baixados.")
                    return todas_pessoas

                first += page_size
                sucesso = True
                tentativas_erro_consecutivo = 0
                break # Sai do loop de tentativas e vai pra proxima pagina
                
            except Exception as e:
                print(f"⚠️ Erro na página {first} (Tentativa {tentativa+1}/3): {e}")
                time.sleep(5) # Espera 5 segundos antes de tentar de novo
        
        if not sucesso:
            print("❌ Falha crítica: Não foi possível baixar a página após 3 tentativas.")
            tentativas_erro_consecutivo += 1
            # Se falhar muitas vezes seguidas, aborta pra não ficar infinito
            if tentativas_erro_consecutivo > 5:
                print("❌ Abortando busca por excesso de erros.")
                break
            # Tenta pular para a próxima página para não travar tudo?
            # Melhor parar e processar o que tem.
            break
            
    return todas_pessoas

def buscar_data_individual(access_token, idt_person):
    """Busca detalhes de uma pessoa"""
    url = f"{BASE_URL}/api/openapi/v1/person/findForEdit"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        response = requests.get(url, params={"code": idt_person}, headers=headers, timeout=20)
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

def processar_aniversariantes_hoje(pessoas, access_token):
    """Processa a lista e busca detalhes SOMENTE de quem vale a pena"""
    
    # Data de Hoje (Brasília)
    tz_br = timezone(timedelta(hours=-3))
    hoje = datetime.now(tz_br)
    dia_hoje = hoje.day
    mes_hoje = hoje.month
    
    print(f"\n🎂 Buscando aniversariantes de: {dia_hoje}/{mes_hoje}")
    
    aniversariantes_confirmados = []
    
    # Otimização: Lista de pessoas para buscar detalhes em paralelo
    # Só vamos buscar detalhes se a gente NÃO achar a data na listagem inicial
    fila_para_buscar_detalhe = []
    
    print("1. Filtrando dados locais...")
    for p in pessoas:
        nome = p.get("namPerson", "")
        # Tenta pegar data do resumo
        dta_raw = p.get("dtaBirth")
        
        # Se tem data no resumo, já verifica
        if dta_raw:
            if verificar_data_match(dta_raw, dia_hoje, mes_hoje):
                # Achou! Adiciona na lista
                aniversariantes_confirmados.append(formatar_pessoa(p, dta_raw))
        else:
            # Se não tem data no resumo, joga pra fila pra buscar detalhe
            if p.get("idtPerson"):
                fila_para_buscar_detalhe.append(p)

    print(f"   - Achados direto na lista: {len(aniversariantes_confirmados)}")
    print(f"   - Precisam buscar detalhe: {len(fila_para_buscar_detalhe)}")
    
    # Busca detalhes em paralelo (limitado para não derrubar a API)
    if fila_para_buscar_detalhe:
        print("2. Buscando detalhes em paralelo (pode demorar)...")
        with ThreadPoolExecutor(max_workers=10) as executor: # Reduzi workers pra evitar erro
            future_to_person = {
                executor.submit(buscar_data_individual, access_token, p["idtPerson"]): p 
                for p in fila_para_buscar_detalhe
            }
            
            total = len(fila_para_buscar_detalhe)
            count = 0
            for future in as_completed(future_to_person):
                p = future_to_person[future]
                count += 1
                if count % 200 == 0: print(f"   Progresso: {count}/{total}")
                
                dta_detalhe = future.result()
                if dta_detalhe and verificar_data_match(dta_detalhe, dia_hoje, mes_hoje):
                    aniversariantes_confirmados.append(formatar_pessoa(p, dta_detalhe))

    return aniversariantes_confirmados

def verificar_data_match(data_raw, dia_alvo, mes_alvo):
    """Verifica se a data bate com o dia/mês alvo"""
    try:
        if isinstance(data_raw, (int, float)):
            dt = datetime.fromtimestamp(data_raw / 1000)
        else:
            # Tenta string ISO
            clean_date = str(data_raw).split("T")[0]
            dt = datetime.strptime(clean_date, "%Y-%m-%d")
            
        return dt.day == dia_alvo and dt.month == mes_alvo
    except:
        return False

def formatar_pessoa(p_dict, data_raw):
    """Extrai telefone e formata dados"""
    # Formata Telefone
    tel = ""
    contact = p_dict.get("contactVOs")
    if isinstance(contact, dict):
        phones = contact.get("phoneVOs", [])
        if phones and len(phones) > 0:
            tel = f"55{phones[0].get('dddPhone','')}{phones[0].get('numPhone','')}"
    
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
            "telefone": pessoa['telefone'], # Já formatado com 55
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

def main():
    print("=== INICIANDO ROBÔ DE ANIVERSÁRIOS BLINDADO ===")
    
    # 1. Auth
    creds = carregar_credentials()
    if not creds: return
    access, new_refresh = obter_access_token(creds['refresh_token'])
    if not access: return
    salvar_credentials({'refresh_token': new_refresh})
    
    # 2. Busca (Com Retry)
    print("\n--- ETAPA 1: Baixar Base de Clientes ---")
    todas_pessoas = buscar_pessoas_blindado(access)
    print(f"Total Final Baixado: {len(todas_pessoas)}")
    
    # 3. Filtro e Envio
    print("\n--- ETAPA 2: Filtrar e Enviar ---")
    aniversariantes = processar_aniversariantes_hoje(todas_pessoas, access)
    
    print(f"\n🎉 Total Aniversariantes Hoje: {len(aniversariantes)}")
    for aniv in aniversariantes:
        enviar_webhook(aniv)
        
    print("\n=== CONCLUÍDO ===")

if __name__ == "__main__":
    main()
