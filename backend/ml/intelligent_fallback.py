# backend/ml/intelligent_fallback.py - VERSÃO 7.0 (DATA-DRIVEN TEMPLATES)
"""
🔥 FALLBACK INTELIGENTE V7.0 - TEMPLATES CONDICIONAIS DATA-DRIVEN
================================================================================
✅ NOVIDADES V7.0:
   - 📊 100% data-driven: usa métricas reais + predições do ML
   - 🎯 Templates condicionais por faixa (não frases genéricas)
   - 🧠 Cada frase incorpora números reais (receita, margem, risco, ticket)
   - 📈 Categorização inteligente por contexto do negócio
   - 🔥 Combina 3 fontes: métricas do arquivo + ML + séries temporais
   - 💬 Muito mais variações: pool de frases por categoria e faixa
   - 🎲 Determinístico (seed baseado em filename) para reprodutibilidade
================================================================================
"""

from __future__ import annotations

import math
import random
from typing import Dict, Any, List, Optional


# ==============================================
# HELPERS
# ==============================================

def _fmt_brl(v: float) -> str:
    try:
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return f"R$ {v:.2f}"


def _fmt_pct(v: float, decimals: int = 1) -> str:
    try:
        return f"{v:.{decimals}f}%".replace(".", ",")
    except Exception:
        return f"{v}%"


def _safe_div(a: float, b: float, default: float = 0.0) -> float:
    try:
        return a / b if b else default
    except Exception:
        return default


def _seed_from(s: str) -> int:
    """Seed determinístico baseado no filename."""
    return abs(hash(s)) % (2 ** 31)


def _pick(pool: List[str], seed: int = 0) -> str:
    if not pool:
        return ""
    return pool[seed % len(pool)]


# ==============================================
# FAIXAS (BUCKETS)
# ==============================================

class MarginBand:
    NEGATIVE = "negativa"
    CRITICAL = "critica"
    LOW      = "baixa"
    MODERATE = "moderada"
    HEALTHY  = "saudavel"
    EXCELLENT= "excelente"

    @staticmethod
    def of(m: float) -> str:
        if m < 0: return MarginBand.NEGATIVE
        if m < 10: return MarginBand.CRITICAL
        if m < 20: return MarginBand.LOW
        if m < 30: return MarginBand.MODERATE
        if m < 45: return MarginBand.HEALTHY
        return MarginBand.EXCELLENT


class RiskBand:
    LOW      = "baixo"
    MODERATE = "moderado"
    HIGH     = "alto"
    CRITICAL = "critico"

    @staticmethod
    def of(pct: float) -> str:
        if pct < 15: return RiskBand.LOW
        if pct < 30: return RiskBand.MODERATE
        if pct < 50: return RiskBand.HIGH
        return RiskBand.CRITICAL


class TicketBand:
    ZERO = "zero"
    LOW = "baixo"
    MEDIUM = "medio"
    HIGH = "alto"
    PREMIUM = "premium"

    @staticmethod
    def of(t: float) -> str:
        if t <= 0: return TicketBand.ZERO
        if t < 100: return TicketBand.LOW
        if t < 500: return TicketBand.MEDIUM
        if t < 2000: return TicketBand.HIGH
        return TicketBand.PREMIUM


class VolumeBand:
    LOW = "baixo"
    MEDIUM = "medio"
    HIGH = "alto"
    VERY_HIGH = "muito_alto"

    @staticmethod
    def of(n: int) -> str:
        if n < 50: return VolumeBand.LOW
        if n < 200: return VolumeBand.MEDIUM
        if n < 1000: return VolumeBand.HIGH
        return VolumeBand.VERY_HIGH


class TrendBand:
    STRONG_UP = "forte_alta"
    UP = "alta"
    STABLE = "estavel"
    DOWN = "queda"
    STRONG_DOWN = "forte_queda"

    @staticmethod
    def of(growth_pct: float) -> str:
        if growth_pct > 30: return TrendBand.STRONG_UP
        if growth_pct > 10: return TrendBand.UP
        if growth_pct > -10: return TrendBand.STABLE
        if growth_pct > -30: return TrendBand.DOWN
        return TrendBand.STRONG_DOWN


# ==============================================
# POOLS DE FRASES POR CATEGORIA E FAIXA
# ==============================================

# ---------- MARGEM ----------

MARGIN_INSIGHTS = {
    MarginBand.NEGATIVE: [
        "A margem de {margin}% coloca a operação em prejuízo: cada venda de {ticket} gera perda líquida de {loss_per_sale}.",
        "Com margem negativa de {margin}%, o prejuízo acumulado é de {abs_profit} — precisa ser revertido com urgência.",
        "Margem de {margin}% significa que a operação paga mais do que arrecada. Ação corretiva é obrigatória.",
    ],
    MarginBand.CRITICAL: [
        "Margem crítica de {margin}% — bem abaixo do piso de 10% que separa saúde de risco operacional.",
        "Com margem em {margin}%, qualquer oscilação de custo pode transformar o resultado em prejuízo.",
        "A margem de {margin}% é insuficiente para cobrir imprevistos: o ideal seria pelo menos 20%.",
    ],
    MarginBand.LOW: [
        "Margem de {margin}% está abaixo do ideal: há espaço para ganho de {gap} p.p. até o patamar saudável (30%).",
        "Com {margin}% de margem, o negócio respira mas não acumula reserva. Cada p.p. ganho vale {per_point}.",
        "Margem baixa de {margin}%: pequenos ajustes de preço/custo podem elevar o lucro de {profit}.",
    ],
    MarginBand.MODERATE: [
        "Margem moderada de {margin}% — aceitável, mas o teto saudável (30%) está a apenas {gap} p.p. de distância.",
        "Com {margin}% de margem, o negócio é sustentável. Otimizações podem levar ao patamar 'saudável'.",
        "Margem de {margin}% está dentro do aceitável. O foco agora é eficiência, não sobrevivência.",
    ],
    MarginBand.HEALTHY: [
        "Margem saudável de {margin}%: a operação cobre custos com folga e gera lucro de {profit}.",
        "Com {margin}% de margem, o negócio tem margem de manobra para investir ou absorver imprevistos.",
        "Margem de {margin}% está dentro da zona saudável do setor — boa notícia para a sustentabilidade.",
    ],
    MarginBand.EXCELLENT: [
        "Margem excelente de {margin}% — acima da média do setor. Lucro de {profit} demonstra forte controle de custos.",
        "Com {margin}% de margem, a operação é referência: alta eficiência e poder de precificação.",
        "Margem de {margin}% coloca o negócio no topo do setor. Considere reinvestir o lucro de {profit}.",
    ],
}

# ---------- RISCO (usa ML) ----------

RISK_INSIGHTS = {
    RiskBand.LOW: [
        "Apenas {high_pct}% dos {n} registros analisados pelo modelo de ML estão em alto risco — base sólida.",
        "O modelo aponta exposição baixa: {high_pct}% em alto risco e {low_pct}% em baixo risco.",
        "Risco controlado: das {n} predições, {n_low} são de baixo risco — nenhum sinal de alerta.",
    ],
    RiskBand.MODERATE: [
        "{high_pct}% dos registros estão em alto risco — dentro do tolerável, mas exige monitoramento.",
        "O ML identificou {n_high} registros em alto risco de {n} totais ({high_pct}%). Atenção contínua.",
        "Exposição moderada: {high_pct}% em alto risco, {low_pct}% em baixo. Equilíbrio razoável.",
    ],
    RiskBand.HIGH: [
        "Alerta: {high_pct}% dos {n} registros são de alto risco pelo modelo preditivo. Ação preventiva recomendada.",
        "O ML detectou concentração preocupante: {n_high} casos em alto risco ({high_pct}%).",
        "Com {high_pct}% em alto risco, a probabilidade de evento adverso sobe — reveja processos.",
    ],
    RiskBand.CRITICAL: [
        "🚨 Situação crítica: {high_pct}% dos {n} registros estão em alto risco segundo o modelo. Intervenção imediata.",
        "O ML sinaliza colapso iminente: {n_high} de {n} registros em alto risco ({high_pct}%).",
        "Nível de risco insustentável: {high_pct}% em alto risco. Priorize mitigação agora.",
    ],
}

# ---------- TICKET MÉDIO ----------

TICKET_INSIGHTS = {
    TicketBand.ZERO: [
        "Nenhum valor médio foi extraído dos dados — verifique a coluna de valor/ticket.",
    ],
    TicketBand.LOW: [
        "Ticket médio de {ticket} é baixo: cada venda contribui pouco para cobrir custos fixos.",
        "Com ticket de {ticket}, são necessárias {n_for_10k} vendas para faturar R$ 10.000.",
        "Ticket médio de {ticket} — oportunidade clara de up-sell e cross-sell.",
    ],
    TicketBand.MEDIUM: [
        "Ticket médio de {ticket} está na faixa esperada para o setor de serviços.",
        "Com ticket de {ticket}, a receita de {revenue} vem de {n} atendimentos.",
        "Ticket médio de {ticket} — patamar saudável. Considere ofertas premium.",
    ],
    TicketBand.HIGH: [
        "Ticket médio alto de {ticket}: cada atendimento contribui significativamente para a receita.",
        "Com {ticket} por atendimento, são necessários apenas {n_for_10k} para R$ 10.000.",
        "Ticket médio de {ticket} — poder de precificação confirmado.",
    ],
    TicketBand.PREMIUM: [
        "Ticket premium de {ticket} — operação com foco em valor, não volume.",
        "Com {ticket} por atendimento, a base de {n} clientes já gera {revenue}.",
        "Ticket de {ticket} coloca o negócio em patamar premium — fidelização é chave.",
    ],
}

# ---------- VOLUME ----------

VOLUME_INSIGHTS = {
    VolumeBand.LOW: [
        "Volume de {n} registros é baixo — a análise estatística tem margem de erro maior.",
        "Com apenas {n} registros, o modelo preditivo foi treinado com dados limitados.",
        "Base de {n} registros — considere ampliar o histórico para maior precisão.",
    ],
    VolumeBand.MEDIUM: [
        "Volume de {n} registros é adequado para análises preditivas confiáveis.",
        "Com {n} registros, o modelo consegue captar padrões com razoável precisão.",
        "Base de {n} registros — dentro do esperado para análises operacionais.",
    ],
    VolumeBand.HIGH: [
        "Volume robusto de {n} registros — análises estatísticas têm alta confiabilidade.",
        "Com {n} registros, o modelo preditivo identifica padrões com boa significância.",
        "Base de {n} registros permite segmentações e análises granulares.",
    ],
    VolumeBand.VERY_HIGH: [
        "Volume muito alto de {n} registros — ideal para modelagem avançada e séries temporais.",
        "Com {n} registros, a análise tem poder estatístico comparável a benchmarks do setor.",
        "Base massiva de {n} registros — permite análise por clusters e personas.",
    ],
}

# ---------- TENDÊNCIA MENSAL ----------

TREND_INSIGHTS = {
    TrendBand.STRONG_UP: [
        "Crescimento forte de {growth}% no período — tendência clara de expansão.",
        "Receita cresceu {growth}% entre os meses analisados. Ritmo acelerado de crescimento.",
        "Tendência fortemente positiva: {growth}% de crescimento. Prepare a operação para escalar.",
    ],
    TrendBand.UP: [
        "Crescimento moderado de {growth}% no período — direção correta.",
        "Receita avançou {growth}% entre os meses — momentum positivo.",
        "Tendência de alta: {growth}% de crescimento consistente.",
    ],
    TrendBand.STABLE: [
        "Receita estável: variação de apenas {growth}% no período analisado.",
        "Tendência lateral com {growth}% de oscilação — negócio em equilíbrio.",
        "Sem tendência clara: receita variou {growth}% entre os meses.",
    ],
    TrendBand.DOWN: [
        "Queda de {abs_growth}% na receita do período — atenção aos indicadores.",
        "Tendência de baixa: {abs_growth}% de queda. Reveja estratégias comerciais.",
        "Receita recuou {abs_growth}% — momento de cautela e revisão de custos.",
    ],
    TrendBand.STRONG_DOWN: [
        "Queda acentuada de {abs_growth}% na receita — situação exige ação imediata.",
        "Retração forte: {abs_growth}% de queda. Priorize retenção de clientes.",
        "Receita despencou {abs_growth}% — investigar causas e reverter com urgência.",
    ],
}

# ---------- CONCENTRAÇÃO SEMANAL ----------

WEEKLY_CONCENTRATION = {
    "alta": [
        "Concentração crítica: {peak_day} responde por {peak_pct}% da receita semanal.",
        "{peak_pct}% da receita semanal vem de {peak_day} — risco de dependência.",
        "Dependência de {peak_day}: {peak_pct}% da receita semanal em um único dia.",
    ],
    "moderada": [
        "Concentração moderada em {peak_day} ({peak_pct}% da receita semanal).",
        "{peak_day} lidera com {peak_pct}% da receita semanal — distribuição razoável.",
        "Pico em {peak_day} com {peak_pct}% — oportunidade de equilibrar os demais dias.",
    ],
    "equilibrada": [
        "Distribuição equilibrada: nenhum dia passa de {peak_pct}% da receita semanal.",
        "Receita bem distribuída na semana — pico de apenas {peak_pct}% em {peak_day}.",
        "Equilíbrio semanal confirmado: {peak_day} lidera com apenas {peak_pct}%.",
    ],
}

WEEKLY_WEAK_DAY = [
    "{weak_day} contribui com apenas {weak_pct}% da receita — dia subutilizado.",
    "Queda em {weak_day}: apenas {weak_pct}% da receita semanal. Considere promoções.",
    "{weak_day} é o ponto fraco da semana ({weak_pct}% da receita).",
]

# ---------- STRENGTHS ----------

STRENGTHS_POOL = {
    "margin": [
        "Margem de {margin}% acima da média do setor",
        "Controle de custos eficaz (margem {margin}%)",
        "Operação lucrativa com margem de {margin}%",
    ],
    "low_risk": [
        "Apenas {high_pct}% em alto risco segundo o ML",
        "Base sólida: {low_pct}% em baixo risco",
        "Exposição controlada: {n_low} de {n} predições em baixo risco",
    ],
    "ticket": [
        "Ticket médio de {ticket} acima da média",
        "Poder de precificação confirmado ({ticket}/atendimento)",
        "Receita por cliente elevada: {ticket}",
    ],
    "volume": [
        "Base robusta de {n} registros",
        "Volume de {n} registros permite análises confiáveis",
        "Histórico consistente de {n} registros",
    ],
    "trend": [
        "Crescimento de {growth}% no período",
        "Tendência positiva consistente ({growth}%)",
        "Momentum de alta: {growth}% de crescimento",
    ],
    "distribution": [
        "Receita bem distribuída na semana",
        "Baixa dependência de um único dia",
        "Equilíbrio semanal com pico de {peak_pct}%",
    ],
}

# ---------- WEAKNESSES ----------

WEAKNESSES_POOL = {
    "margin": [
        "Margem de apenas {margin}%",
        "Margem {margin_class} ({margin}%)",
        "Margem abaixo do ideal: {margin}%",
    ],
    "high_risk": [
        "{high_pct}% em alto risco (ML)",
        "Concentração de risco: {n_high} registros críticos",
        "Exposição elevada: {high_pct}% em alto risco",
    ],
    "ticket": [
        "Ticket médio baixo ({ticket})",
        "Receita por atendimento abaixo do ideal ({ticket})",
        "Ticket de {ticket} limita o crescimento",
    ],
    "trend": [
        "Queda de {abs_growth}% no período",
        "Tendência de baixa ({growth}%)",
        "Receita em retração ({abs_growth}%)",
    ],
    "concentration": [
        "{peak_pct}% da receita semanal concentrada em {peak_day}",
        "Dependência de {peak_day} ({peak_pct}%)",
        "Alta concentração semanal em {peak_day}",
    ],
    "volatility": [
        "Volatilidade mensal de {cv}%",
        "Receita imprevisível (CV={cv}%)",
        "Alta variação mensal ({cv}%)",
    ],
}

# ---------- RECOMMENDATIONS ----------

RECOMMENDATIONS_POOL = {
    "margin_negative": [
        "Revisar imediatamente a precificação: cada atendimento a {ticket} gera prejuízo de {loss_per_sale}.",
        "Cortar custos operacionais em pelo menos {cut_needed_pct}% para reverter a margem de {margin}%.",
        "Renegociar fornecedores e reavaliar mix de serviços: margem de {margin}% é insustentável.",
    ],
    "margin_critical": [
        "Aumentar preço médio em {price_increase_pct}% ou reduzir custo em {cost_cut_pct}% para atingir margem saudável.",
        "Revisar contrato de fornecedores: a margem de {margin}% precisa subir para pelo menos 20%.",
        "Focar em serviços de maior valor agregado para elevar a margem de {margin}%.",
    ],
    "margin_low": [
        "Otimizar mix de serviços: ganho de {gap} p.p. na margem adiciona {additional_profit} ao lucro.",
        "Negociar com fornecedores: cada 1% de redução de custo adiciona {per_point} ao resultado.",
        "Aumentar ticket médio em 10% via up-sell para elevar margem de {margin}%.",
    ],
    "margin_moderate": [
        "Explorar serviços premium para elevar margem de {margin}% ao patamar saudável (30%+).",
        "Automatizar processos para reduzir custo fixo e ganhar {gap} p.p. de margem.",
        "Fidelizar clientes atuais: aumento de 5% na retenção eleva margem em ~2 p.p.",
    ],
    "margin_excellent": [
        "Reinvestir o lucro de {profit} em expansão ou reserva estratégica.",
        "Considerar aumento de capacidade para escalar a operação de alta margem ({margin}%).",
        "Documentar práticas atuais como benchmark interno para outras unidades.",
    ],
    "risk_high": [
        "Priorizar os {n_high} registros em alto risco: ação preventiva sobre os {high_pct}% críticos.",
        "Criar plano de mitigação focado nos {n_high} casos sinalizados pelo ML.",
        "Revisar processo operacional: {high_pct}% dos registros em alto risco indica falha sistêmica.",
    ],
    "risk_moderate": [
        "Monitorar continuamente os {n_high} registros em alto risco ({high_pct}%).",
        "Criar alertas automáticos para os casos com score > 0.7.",
        "Investigar correlação entre os {n_high} casos de alto risco para achar causa raiz.",
    ],
    "risk_low": [
        "Manter monitoramento padrão: risco controlado em {high_pct}%.",
        "Aproveitar a base sólida para investir em crescimento.",
        "Documentar práticas que mantêm o risco baixo para replicar.",
    ],
    "ticket_low": [
        "Oferecer combos/up-sell: elevar ticket de {ticket} em 20% aumenta receita em {ticket_gain_20pct}.",
        "Treinar equipe em técnicas de venda adicional.",
        "Criar pacotes de serviços com preço premium.",
    ],
    "ticket_medium": [
        "Introduzir serviços premium para elevar o ticket médio acima de R$ 1.000.",
        "Oferecer planos de manutenção recorrente para estabilizar a receita.",
        "Investir em marketing de relacionamento para aumentar frequência de visita.",
    ],
    "trend_down": [
        "Investigar causa da queda de {abs_growth}%: preço, demanda ou concorrência?",
        "Reforçar marketing para reverter tendência de baixa.",
        "Reativar clientes inativos para recuperar receita.",
    ],
    "trend_up": [
        "Preparar operação para absorver crescimento de {growth}% — capacidade, equipe, estoque.",
        "Documentar o que gerou o crescimento para replicar.",
        "Considerar investimento em expansão aproveitando o momentum.",
    ],
    "concentration": [
        "Diversificar receita: reduzir dependência de {peak_day} ({peak_pct}% da receita).",
        "Criar promoções em {weak_day} (apenas {weak_pct}% da receita).",
        "Equilibrar demanda semanal com campanhas segmentadas por dia.",
    ],
    "volatility": [
        "Reduzir volatilidade de {cv}% com contratos recorrentes ou assinaturas.",
        "Criar reserva de caixa para absorver meses fracos.",
        "Estabilizar receita com serviços recorrentes (manutenção preventiva).",
    ],
    "high_volume": [
        "Explorar segmentação por perfil de cliente para personalizar ofertas.",
        "Automatizar atendimento inicial para lidar com o volume de {n} registros.",
        "Investir em CRM para fidelização em escala.",
    ],
}


# ==============================================
# MOTOR PRINCIPAL
# ==============================================

class IntelligentAnalyzerV7:
    """
    🔥 Analisador data-driven que combina:
      - Métricas reais do arquivo (receita, custo, margem, ticket, volume)
      - Predições do ML (score médio, % alto risco, distribuição)
      - Séries temporais (crescimento mensal, concentração semanal, CV)
    """

    # -------------- API PÚBLICA --------------

    @staticmethod
    def analyze_file(file_metrics) -> Dict[str, Any]:
        ctx = IntelligentAnalyzerV7._build_context(file_metrics)
        seed = _seed_from(file_metrics.filename)

        insights: List[str] = []
        strengths: List[str] = []
        weaknesses: List[str] = []
        recommendations: List[Dict[str, Any]] = []

        IntelligentAnalyzerV7._fill_margin(ctx, seed, insights, strengths, weaknesses, recommendations)
        IntelligentAnalyzerV7._fill_risk(ctx, seed, insights, strengths, weaknesses, recommendations)
        IntelligentAnalyzerV7._fill_ticket(ctx, seed, insights, strengths, weaknesses, recommendations)
        IntelligentAnalyzerV7._fill_volume(ctx, seed, insights, strengths)
        IntelligentAnalyzerV7._fill_trend(ctx, seed, insights, strengths, weaknesses, recommendations)
        IntelligentAnalyzerV7._fill_weekly(ctx, seed, insights, strengths, weaknesses, recommendations)
        IntelligentAnalyzerV7._fill_volatility(ctx, seed, insights, weaknesses, recommendations)

        summary = IntelligentAnalyzerV7._build_file_summary(ctx)
        score = IntelligentAnalyzerV7._calculate_score(ctx)

        return {
            "insights": insights,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "recommendations": recommendations,
            "metrics_extra": ctx,
            "summary": summary,
            "score": score,
        }

    @staticmethod
    def analyze_multiple_files(consolidated) -> Dict[str, Any]:
        files = consolidated.files
        if not files:
            return IntelligentAnalyzerV7._empty_analysis()

        per_file = {f.filename: IntelligentAnalyzerV7.analyze_file(f) for f in files}

        scores = [a["score"] for a in per_file.values()]
        avg_score = sum(scores) / len(scores) if scores else 5.0

        comparison = IntelligentAnalyzerV7._compare_files(files, consolidated) if len(files) > 1 else {}
        trend = IntelligentAnalyzerV7._aggregate_trend(files, consolidated)

        all_recs = []
        seen = set()
        for fname, a in per_file.items():
            for r in a["recommendations"]:
                key = r["description"][:80]
                if key in seen:
                    continue
                seen.add(key)
                r2 = dict(r)
                if len(files) > 1:
                    r2["source_file"] = fname
                all_recs.append(r2)

        prio = {"alta": 0, "media": 1, "baixa": 2}
        all_recs.sort(key=lambda r: prio.get(r.get("priority", "media"), 1))
        all_recs = all_recs[:10]

        exec_score = IntelligentAnalyzerV7._build_executive_score(consolidated, per_file, avg_score)
        exec_summary = IntelligentAnalyzerV7._build_executive_summary(consolidated, per_file, comparison)
        forecast = IntelligentAnalyzerV7._build_forecast(consolidated, trend)
        conclusion = IntelligentAnalyzerV7._build_conclusion(consolidated, per_file, avg_score)

        combined_insights = []
        for fname, a in per_file.items():
            for ins in a["insights"][:3]:
                combined_insights.append(f"[{fname}] {ins}" if len(files) > 1 else ins)

        return {
            "success": True,
            "executive_score": exec_score,
            "executive_summary": exec_summary,
            "comparison": comparison,
            "trend": trend,
            "recommendations": all_recs,
            "forecast": forecast,
            "conclusion": conclusion,
            "combined_insights": combined_insights[:12],
            "per_file_analysis": per_file,
            "model_used": "intelligent_fallback_v7",
            "tokens_used": 0,
            "response_time_ms": 0,
            "fallback_used": True,
            "full_analysis": exec_summary + "\n\n" + conclusion,
        }

    # -------------- CONTEXTO --------------

    @staticmethod
    def _build_context(f) -> Dict[str, Any]:
        predictions = list(f.predictions or [])
        n = len(predictions)

        if predictions:
            avg_score = sum(predictions) / n
            high_risk = [p for p in predictions if p > 0.7]
            low_risk = [p for p in predictions if p < 0.3]
            n_high = len(high_risk)
            n_low = len(low_risk)
            high_pct = (n_high / n) * 100
            low_pct = (n_low / n) * 100
            variance = sum((p - avg_score) ** 2 for p in predictions) / n
            std_score = math.sqrt(variance)
        else:
            avg_score = 0.5; std_score = 0.0
            n_high = n_low = 0
            high_pct = low_pct = 0.0

        revenue = float(f.total_revenue or 0)
        cost = float(f.total_costs or 0)
        profit = float(f.profit or 0)
        margin = float(f.margin or 0)
        rows = int(f.total_rows or 0)

        ticket = _safe_div(revenue, rows, 0)
        cost_per_row = _safe_div(cost, rows, 0)
        profit_per_row = _safe_div(profit, rows, 0)

        chart = f.chart_data or {}
        monthly_rev = chart.get("monthly", {}).get("revenue", [])
        valid_months = [float(v) for v in monthly_rev if v and v > 0]
        growth = 0.0
        cv = 0.0
        if len(valid_months) >= 2:
            growth = _safe_div((valid_months[-1] - valid_months[0]) * 100, valid_months[0], 0)
        if len(valid_months) >= 3:
            mean_v = sum(valid_months) / len(valid_months)
            var = sum((v - mean_v) ** 2 for v in valid_months) / len(valid_months)
            std_v = math.sqrt(var)
            cv = _safe_div(std_v * 100, mean_v, 0)

        weekly_rev = chart.get("weekly", {}).get("revenue", [])
        days = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
        peak_day = weak_day = ""
        peak_pct = weak_pct = 0.0
        if weekly_rev and sum(weekly_rev) > 0:
            total_week = sum(weekly_rev)
            max_i = max(range(len(weekly_rev)), key=lambda i: weekly_rev[i])
            min_i = min(range(len(weekly_rev)), key=lambda i: weekly_rev[i])
            peak_day = days[max_i] if max_i < len(days) else f"Dia {max_i+1}"
            weak_day = days[min_i] if min_i < len(days) else f"Dia {min_i+1}"
            peak_pct = weekly_rev[max_i] / total_week * 100
            weak_pct = weekly_rev[min_i] / total_week * 100

        # Derivados para templates
        margin_gap = max(0.0, 30 - margin) if margin < 30 else 0.0
        per_point_margin = revenue * 0.01 if revenue else 0
        loss_per_sale = max(0.0, cost_per_row - ticket)
        abs_profit = abs(profit)
        price_increase_pct = 0.0
        cost_cut_pct = 0.0
        cut_needed_pct = 0.0
        if revenue > 0 and profit < 0:
            price_increase_pct = abs(profit) / revenue * 100
            cut_needed_pct = price_increase_pct
        if revenue > 0:
            cost_cut_pct = max(0.0, (cost / revenue * 100) - (100 - 30))  # p/ chegar a 30% margem
        additional_profit = revenue * 0.10
        ticket_gain_20pct = ticket * 0.20 * rows
        n_for_10k = int(10000 / ticket) if ticket > 0 else 0

        return {
            "filename": f.filename,
            "rows": rows,
            "revenue": revenue,
            "revenue_fmt": _fmt_brl(revenue),
            "cost": cost,
            "cost_fmt": _fmt_brl(cost),
            "profit": profit,
            "profit_fmt": _fmt_brl(profit),
            "abs_profit_fmt": _fmt_brl(abs_profit),
            "margin": margin,
            "margin_fmt": _fmt_pct(margin),
            "ticket": ticket,
            "ticket_fmt": _fmt_brl(ticket),
            "cost_per_row": cost_per_row,
            "profit_per_row": profit_per_row,

            "n": n,
            "avg_score": avg_score,
            "std_score": std_score,
            "high_pct": high_pct,
            "high_pct_fmt": _fmt_pct(high_pct),
            "low_pct": low_pct,
            "low_pct_fmt": _fmt_pct(low_pct),
            "n_high": n_high,
            "n_low": n_low,

            "growth": growth,
            "growth_fmt": _fmt_pct(growth),
            "abs_growth": abs(growth),
            "abs_growth_fmt": _fmt_pct(abs(growth)),
            "monthly_cv": cv,
            "cv_fmt": _fmt_pct(cv),

            "peak_day": peak_day or "-",
            "peak_pct": peak_pct,
            "peak_pct_fmt": _fmt_pct(peak_pct),
            "weak_day": weak_day or "-",
            "weak_pct": weak_pct,
            "weak_pct_fmt": _fmt_pct(weak_pct),

            # derivados
            "gap": _fmt_pct(margin_gap, 1),
            "gap_num": margin_gap,
            "per_point": _fmt_brl(per_point_margin),
            "loss_per_sale": _fmt_brl(loss_per_sale),
            "price_increase_pct": _fmt_pct(price_increase_pct),
            "cost_cut_pct": _fmt_pct(cost_cut_pct),
            "cut_needed_pct": _fmt_pct(cut_needed_pct),
            "additional_profit": _fmt_brl(additional_profit),
            "ticket_gain_20pct": _fmt_brl(ticket_gain_20pct),
            "n_for_10k": n_for_10k,

            # bandas
            "margin_band": MarginBand.of(margin),
            "risk_band": RiskBand.of(high_pct),
            "ticket_band": TicketBand.of(ticket),
            "volume_band": VolumeBand.of(rows),
            "trend_band": TrendBand.of(growth),
        }

    # -------------- FILLERS --------------

    @staticmethod
    def _safe_format(template: str, ctx: Dict[str, Any]) -> str:
        try:
            return template.format(**ctx)
        except (KeyError, IndexError):
            return template

    @staticmethod
    def _fill_margin(ctx, seed, insights, strengths, weaknesses, recommendations):
        band = ctx["margin_band"]
        pool = MARGIN_INSIGHTS.get(band, [])
        if pool:
            insights.append(IntelligentAnalyzerV7._safe_format(_pick(pool, seed), ctx))

        margin = ctx["margin"]
        if band == MarginBand.NEGATIVE:
            weaknesses.append(IntelligentAnalyzerV7._safe_format(
                _pick(WEAKNESSES_POOL["margin"], seed), ctx))
            recommendations.append({
                "priority": "alta", "category": "financeiro",
                "description": IntelligentAnalyzerV7._safe_format(
                    _pick(RECOMMENDATIONS_POOL["margin_negative"], seed), ctx),
                "expected_impact": "Crítico", "effort": "alto",
            })
        elif band == MarginBand.CRITICAL:
            weaknesses.append(IntelligentAnalyzerV7._safe_format(
                _pick(WEAKNESSES_POOL["margin"], seed), ctx))
            recommendations.append({
                "priority": "alta", "category": "financeiro",
                "description": IntelligentAnalyzerV7._safe_format(
                    _pick(RECOMMENDATIONS_POOL["margin_critical"], seed), ctx),
                "expected_impact": "Alto", "effort": "alto",
            })
        elif band == MarginBand.LOW:
            weaknesses.append(IntelligentAnalyzerV7._safe_format(
                _pick(WEAKNESSES_POOL["margin"], seed), ctx))
            recommendations.append({
                "priority": "media", "category": "financeiro",
                "description": IntelligentAnalyzerV7._safe_format(
                    _pick(RECOMMENDATIONS_POOL["margin_low"], seed), ctx),
                "expected_impact": "Médio", "effort": "medio",
            })
        elif band == MarginBand.MODERATE:
            recommendations.append({
                "priority": "media", "category": "financeiro",
                "description": IntelligentAnalyzerV7._safe_format(
                    _pick(RECOMMENDATIONS_POOL["margin_moderate"], seed), ctx),
                "expected_impact": "Médio", "effort": "medio",
            })
        elif band in (MarginBand.HEALTHY, MarginBand.EXCELLENT):
            strengths.append(IntelligentAnalyzerV7._safe_format(
                _pick(STRENGTHS_POOL["margin"], seed), ctx))
            if band == MarginBand.EXCELLENT:
                recommendations.append({
                    "priority": "baixa", "category": "financeiro",
                    "description": IntelligentAnalyzerV7._safe_format(
                        _pick(RECOMMENDATIONS_POOL["margin_excellent"], seed), ctx),
                    "expected_impact": "Alto", "effort": "baixo",
                })

    @staticmethod
    def _fill_risk(ctx, seed, insights, strengths, weaknesses, recommendations):
        band = ctx["risk_band"]
        if ctx["n"] == 0:
            return
        pool = RISK_INSIGHTS.get(band, [])
        if pool:
            insights.append(IntelligentAnalyzerV7._safe_format(_pick(pool, seed + 1), ctx))

        if band == RiskBand.LOW:
            strengths.append(IntelligentAnalyzerV7._safe_format(
                _pick(STRENGTHS_POOL["low_risk"], seed + 1), ctx))
            recommendations.append({
                "priority": "baixa", "category": "operacional",
                "description": IntelligentAnalyzerV7._safe_format(
                    _pick(RECOMMENDATIONS_POOL["risk_low"], seed + 1), ctx),
                "expected_impact": "Baixo", "effort": "baixo",
            })
        elif band == RiskBand.MODERATE:
            recommendations.append({
                "priority": "media", "category": "operacional",
                "description": IntelligentAnalyzerV7._safe_format(
                    _pick(RECOMMENDATIONS_POOL["risk_moderate"], seed + 1), ctx),
                "expected_impact": "Médio", "effort": "medio",
            })
        elif band in (RiskBand.HIGH, RiskBand.CRITICAL):
            weaknesses.append(IntelligentAnalyzerV7._safe_format(
                _pick(WEAKNESSES_POOL["high_risk"], seed + 1), ctx))
            recommendations.append({
                "priority": "alta", "category": "operacional",
                "description": IntelligentAnalyzerV7._safe_format(
                    _pick(RECOMMENDATIONS_POOL["risk_high"], seed + 2), ctx),
                "expected_impact": "Alto", "effort": "alto",
            })

    @staticmethod
    def _fill_ticket(ctx, seed, insights, strengths, weaknesses, recommendations):
        band = ctx["ticket_band"]
        pool = TICKET_INSIGHTS.get(band, [])
        if pool:
            insights.append(IntelligentAnalyzerV7._safe_format(_pick(pool, seed + 2), ctx))

        if band in (TicketBand.HIGH, TicketBand.PREMIUM):
            strengths.append(IntelligentAnalyzerV7._safe_format(
                _pick(STRENGTHS_POOL["ticket"], seed + 2), ctx))
        elif band == TicketBand.LOW:
            weaknesses.append(IntelligentAnalyzerV7._safe_format(
                _pick(WEAKNESSES_POOL["ticket"], seed + 2), ctx))
            recommendations.append({
                "priority": "media", "category": "comercial",
                "description": IntelligentAnalyzerV7._safe_format(
                    _pick(RECOMMENDATIONS_POOL["ticket_low"], seed + 2), ctx),
                "expected_impact": "Médio", "effort": "baixo",
            })
        elif band == TicketBand.MEDIUM:
            recommendations.append({
                "priority": "baixa", "category": "comercial",
                "description": IntelligentAnalyzerV7._safe_format(
                    _pick(RECOMMENDATIONS_POOL["ticket_medium"], seed + 3), ctx),
                "expected_impact": "Médio", "effort": "medio",
            })

    @staticmethod
    def _fill_volume(ctx, seed, insights, strengths):
        band = ctx["volume_band"]
        pool = VOLUME_INSIGHTS.get(band, [])
        if pool:
            insights.append(IntelligentAnalyzerV7._safe_format(_pick(pool, seed + 3), ctx))
        if band in (VolumeBand.HIGH, VolumeBand.VERY_HIGH):
            strengths.append(IntelligentAnalyzerV7._safe_format(
                _pick(STRENGTHS_POOL["volume"], seed + 3), ctx))

    @staticmethod
    def _fill_trend(ctx, seed, insights, strengths, weaknesses, recommendations):
        band = ctx["trend_band"]
        if not ctx.get("growth"):
            return
        pool = TREND_INSIGHTS.get(band, [])
        if pool:
            insights.append(IntelligentAnalyzerV7._safe_format(_pick(pool, seed + 4), ctx))

        if band in (TrendBand.STRONG_UP, TrendBand.UP):
            strengths.append(IntelligentAnalyzerV7._safe_format(
                _pick(STRENGTHS_POOL["trend"], seed + 4), ctx))
            recommendations.append({
                "priority": "baixa", "category": "operacional",
                "description": IntelligentAnalyzerV7._safe_format(
                    _pick(RECOMMENDATIONS_POOL["trend_up"], seed + 4), ctx),
                "expected_impact": "Alto", "effort": "medio",
            })
        elif band in (TrendBand.DOWN, TrendBand.STRONG_DOWN):
            weaknesses.append(IntelligentAnalyzerV7._safe_format(
                _pick(WEAKNESSES_POOL["trend"], seed + 4), ctx))
            recommendations.append({
                "priority": "alta", "category": "operacional",
                "description": IntelligentAnalyzerV7._safe_format(
                    _pick(RECOMMENDATIONS_POOL["trend_down"], seed + 5), ctx),
                "expected_impact": "Alto", "effort": "alto",
            })

    @staticmethod
    def _fill_weekly(ctx, seed, insights, strengths, weaknesses, recommendations):
        if not ctx.get("peak_day") or ctx["peak_day"] == "-":
            return
        peak_pct = ctx["peak_pct"]
        if peak_pct > 40:
            conc = "alta"
            weaknesses.append(IntelligentAnalyzerV7._safe_format(
                _pick(WEAKNESSES_POOL["concentration"], seed + 5), ctx))
        elif peak_pct > 25:
            conc = "moderada"
        else:
            conc = "equilibrada"
            strengths.append(IntelligentAnalyzerV7._safe_format(
                _pick(STRENGTHS_POOL["distribution"], seed + 5), ctx))

        pool = WEEKLY_CONCENTRATION.get(conc, [])
        if pool:
            insights.append(IntelligentAnalyzerV7._safe_format(_pick(pool, seed + 5), ctx))

        if ctx["weak_pct"] > 0 and ctx["weak_pct"] < 5:
            insights.append(IntelligentAnalyzerV7._safe_format(
                _pick(WEEKLY_WEAK_DAY, seed + 6), ctx))

        if conc == "alta":
            recommendations.append({
                "priority": "media", "category": "operacional",
                "description": IntelligentAnalyzerV7._safe_format(
                    _pick(RECOMMENDATIONS_POOL["concentration"], seed + 6), ctx),
                "expected_impact": "Médio", "effort": "medio",
            })

    @staticmethod
    def _fill_volatility(ctx, seed, insights, weaknesses, recommendations):
        cv = ctx.get("monthly_cv", 0)
        if cv and cv > 50:
            weaknesses.append(IntelligentAnalyzerV7._safe_format(
                _pick(WEAKNESSES_POOL["volatility"], seed + 7), ctx))
            recommendations.append({
                "priority": "media", "category": "financeiro",
                "description": IntelligentAnalyzerV7._safe_format(
                    _pick(RECOMMENDATIONS_POOL["volatility"], seed + 7), ctx),
                "expected_impact": "Médio", "effort": "alto",
            })

    # -------------- SUMÁRIO DO ARQUIVO --------------

    @staticmethod
    def _build_file_summary(ctx: Dict[str, Any]) -> str:
        parts = []
        parts.append(
            f"O arquivo '{ctx['filename']}' contém {ctx['rows']} registros "
            f"com receita total de {ctx['revenue_fmt']} e lucro de {ctx['profit_fmt']}."
        )

        margin_desc = {
            MarginBand.NEGATIVE: f"A margem negativa de {ctx['margin_fmt']} exige ação corretiva imediata.",
            MarginBand.CRITICAL: f"A margem crítica de {ctx['margin_fmt']} está bem abaixo do ideal.",
            MarginBand.LOW: f"A margem de {ctx['margin_fmt']} está abaixo do esperado para o setor.",
            MarginBand.MODERATE: f"A margem de {ctx['margin_fmt']} é aceitável, com espaço para otimização.",
            MarginBand.HEALTHY: f"A margem saudável de {ctx['margin_fmt']} indica boa gestão financeira.",
            MarginBand.EXCELLENT: f"A margem excelente de {ctx['margin_fmt']} demonstra performance superior.",
        }
        parts.append(margin_desc.get(ctx["margin_band"], ""))

        vol_desc = {
            VolumeBand.LOW: "O volume de dados é baixo, o que pode limitar a precisão.",
            VolumeBand.MEDIUM: "O volume de dados é adequado para análises confiáveis.",
            VolumeBand.HIGH: "O volume de dados é robusto, permitindo análises sólidas.",
            VolumeBand.VERY_HIGH: "O volume de dados é muito alto, ideal para modelagem avançada.",
        }
        parts.append(vol_desc.get(ctx["volume_band"], ""))

        if ctx["n"] > 0:
            if ctx["high_pct"] > 50:
                parts.append(f"Preocupação: {ctx['high_pct_fmt']} dos registros são de alto risco pelo ML.")
            elif ctx["high_pct"] < 15:
                parts.append(f"Base sólida: apenas {ctx['high_pct_fmt']} em alto risco.")

        if ctx["peak_pct"] > 35 and ctx["peak_day"] != "-":
            parts.append(f"Concentração em {ctx['peak_day']} ({ctx['peak_pct_fmt']} da receita semanal).")

        if ctx["growth"] > 15:
            parts.append(f"Tendência mensal positiva (+{ctx['growth_fmt']}).")
        elif ctx["growth"] < -15:
            parts.append(f"Tendência mensal negativa ({ctx['growth_fmt']}).")

        return " ".join(p for p in parts if p)

    # -------------- SCORE --------------

    @staticmethod
    def _calculate_score(ctx: Dict[str, Any]) -> float:
        score = 5.0
        margin = ctx["margin"]
        if margin >= 45: score += 3.0
        elif margin >= 30: score += 2.0
        elif margin >= 20: score += 1.0
        elif margin >= 10: score += 0.0
        elif margin >= 0: score -= 1.5
        else: score -= 3.0

        high_pct = ctx["high_pct"]
        if high_pct < 15: score += 2.0
        elif high_pct < 30: score += 1.0
        elif high_pct < 50: score -= 1.0
        else: score -= 2.0

        growth = ctx["growth"]
        if growth > 20: score += 1.5
        elif growth > 5: score += 0.75
        elif growth < -20: score -= 1.5
        elif growth < -5: score -= 0.75

        cv = ctx["monthly_cv"]
        if cv and cv < 20: score += 1.0
        elif cv and cv < 40: score += 0.5
        elif cv and cv > 60: score -= 1.0

        return max(0.0, min(10.0, score))

    # -------------- COMPARAÇÃO MULTI-ARQUIVO --------------

    @staticmethod
    def _compare_files(files, consolidated) -> Dict[str, Any]:
        if len(files) < 2:
            return {}

        by_revenue = sorted(files, key=lambda f: f.total_revenue, reverse=True)
        by_profit = sorted(files, key=lambda f: f.profit, reverse=True)
        by_margin = sorted(files, key=lambda f: f.margin, reverse=True)
        by_risk = sorted(files, key=lambda f: f.high_risk_percentage)

        parts = []
        best = by_revenue[0]; worst = by_revenue[-1]
        diff_pct = _safe_div(
            (best.total_revenue - worst.total_revenue) * 100,
            worst.total_revenue, 0,
        )
        parts.append(
            f"'{best.filename}' lidera com {_fmt_brl(best.total_revenue)} "
            f"({_fmt_pct(diff_pct)} acima de '{worst.filename}')."
        )
        riskiest = max(files, key=lambda f: f.high_risk_percentage)
        if riskiest.high_risk_percentage > 30:
            parts.append(
                f"'{riskiest.filename}' tem {_fmt_pct(riskiest.high_risk_percentage)} de alto risco."
            )
        best_margin = by_margin[0]
        parts.append(f"Melhor margem: '{best_margin.filename}' com {_fmt_pct(best_margin.margin)}.")

        return {
            "best_revenue": by_revenue[0].filename,
            "best_profit": by_profit[0].filename,
            "best_growth": by_margin[0].filename,
            "best_efficiency": by_margin[0].filename,
            "highest_risk": riskiest.filename,
            "lowest_performance": by_revenue[-1].filename,
            "summary": " ".join(parts),
            "ranking_revenue": [f.filename for f in by_revenue],
            "ranking_profit": [f.filename for f in by_profit],
            "ranking_margin": [f.filename for f in by_margin],
        }

    @staticmethod
    def _aggregate_trend(files, consolidated) -> Dict[str, Any]:
        if len(files) < 2:
            return {
                "direction": "estavel", "strength": 0.5, "confidence": 0.5,
                "description": "Dados insuficientes para análise de tendência.",
                "key_observations": [],
            }
        sorted_files = sorted(files, key=lambda f: f.filename)
        revenues = [f.total_revenue for f in sorted_files]
        growth = _safe_div((revenues[-1] - revenues[0]) * 100, revenues[0], 0) if revenues[0] > 0 else 0

        if growth > 10:
            return {
                "direction": "crescente", "strength": round(min(1.0, growth / 50), 2),
                "confidence": 0.75,
                "description": f"Tendência de crescimento de {_fmt_pct(growth)} entre os arquivos.",
                "key_observations": [f"Receita cresceu {_fmt_pct(growth)}"],
            }
        elif growth < -10:
            return {
                "direction": "decrescente", "strength": round(min(1.0, abs(growth) / 50), 2),
                "confidence": 0.75,
                "description": f"Tendência de queda de {_fmt_pct(abs(growth))} entre os arquivos.",
                "key_observations": [f"Receita caiu {_fmt_pct(abs(growth))}"],
            }
        else:
            return {
                "direction": "estavel", "strength": 0.5, "confidence": 0.75,
                "description": f"Estabilidade no período (variação de {_fmt_pct(growth)}).",
                "key_observations": ["Receita estável"],
            }

    # -------------- EXECUTIVE --------------

    @staticmethod
    def _build_executive_score(consolidated, per_file, avg_score):
        margin = consolidated.avg_margin
        if margin < 0: saude = 1.0
        elif margin < 10: saude = 3.0
        elif margin < 20: saude = 5.0
        elif margin < 30: saude = 7.0
        elif margin < 45: saude = 8.5
        else: saude = 10.0

        eficiencia = min(10.0, avg_score)

        if consolidated.total_revenue > 0:
            cost_ratio = (consolidated.total_revenue - consolidated.total_profit) / consolidated.total_revenue
            if cost_ratio < 0.5: controle = 9.0
            elif cost_ratio < 0.65: controle = 7.0
            elif cost_ratio < 0.8: controle = 5.0
            elif cost_ratio < 0.95: controle = 3.0
            else: controle = 1.0
        else:
            controle = 5.0

        growth = 5.0
        nivel = "Moderado"
        if consolidated.ml_results and consolidated.ml_results.total_predictions > 0:
            high_risk = consolidated.ml_results.risk_distribution.get("alto", 0)
            if high_risk < 15: growth = 8.0; nivel = "Baixo"
            elif high_risk < 30: growth = 6.0; nivel = "Moderado"
            elif high_risk < 50: growth = 4.0; nivel = "Moderado"
            else: growth = 2.0; nivel = "Alto"

        nota_geral = (saude + eficiencia + controle + growth) / 4
        return {
            "saude_financeira": round(saude, 1),
            "eficiencia": round(eficiencia, 1),
            "controle_custos": round(controle, 1),
            "crescimento": round(growth, 1),
            "nivel_risco": nivel,
            "nota_geral": round(nota_geral, 1),
        }

    @staticmethod
    def _build_executive_summary(consolidated, per_file, comparison):
        parts = []
        n_files = consolidated.processed_files
        total_rows = sum(f.total_rows for f in consolidated.files)

        if n_files == 1:
            parts.append(f"Análise completa de '{consolidated.files[0].filename}' com {total_rows} registros.")
        else:
            parts.append(f"Análise comparativa de {n_files} arquivos com {total_rows} registros no total.")

        parts.append(
            f"Receita total de {_fmt_brl(consolidated.total_revenue)}, "
            f"lucro de {_fmt_brl(consolidated.total_profit)} "
            f"e margem média de {_fmt_pct(consolidated.avg_margin)}."
        )

        margin = consolidated.avg_margin
        if margin >= 45: parts.append("A margem está em nível excelente, acima da média do setor.")
        elif margin >= 30: parts.append("A margem é saudável e sustentável.")
        elif margin >= 20: parts.append("A margem é aceitável, mas há espaço para otimização.")
        elif margin >= 10: parts.append("A margem é baixa — atenção aos custos operacionais.")
        elif margin >= 0: parts.append("A margem é crítica — ação corretiva necessária.")
        else: parts.append("A operação está em prejuízo — intervenção imediata requerida.")

        if comparison and comparison.get("summary"):
            parts.append(comparison["summary"])

        if consolidated.ml_results:
            high = consolidated.ml_results.risk_distribution.get("alto", 0)
            if high > 40:
                parts.append(f"Alerta: {_fmt_pct(high)} dos registros em alto risco pelo ML.")
            elif high < 15:
                parts.append(f"Base sólida: apenas {_fmt_pct(high)} em alto risco.")

        return " ".join(parts)

    @staticmethod
    def _build_forecast(consolidated, trend):
        margin = consolidated.avg_margin
        direction = trend.get("direction", "estavel")

        if margin >= 30 and direction == "crescente":
            return ("Cenário otimista: com margem saudável e tendência de crescimento, "
                    "espera-se expansão sustentada. Prepare a estrutura para absorver aumento de demanda.")
        elif margin >= 20 and direction == "crescente":
            return ("Cenário positivo: margem aceitável combinada com crescimento. "
                    "Mantenha o foco em eficiência para consolidar a expansão.")
        elif margin >= 30 and direction == "estavel":
            return ("Cenário estável: margem saudável com receita consistente. "
                    "Boa base para investimentos em crescimento planejado.")
        elif margin < 10 and direction == "decrescente":
            return ("Cenário de atenção: margem baixa com tendência de queda. "
                    "Ação corretiva urgente para reverter o quadro.")
        elif margin < 20 and direction == "decrescente":
            return ("Cenário de cautela: margem sob pressão e receita em queda. "
                    "Revisar precificação e estrutura de custos.")
        elif margin < 10:
            return ("Cenário crítico: margem baixa exige intervenção. "
                    "Priorizar corte de custos e renegociação com fornecedores.")
        else:
            return ("Cenário neutro: indicadores estáveis. "
                    "Manter monitoramento contínuo e buscar oportunidades de otimização.")

    @staticmethod
    def _build_conclusion(consolidated, per_file, avg_score):
        parts = []
        if avg_score >= 8: parts.append(f"Desempenho geral excelente (score {avg_score:.1f}/10).")
        elif avg_score >= 6: parts.append(f"Desempenho geral bom (score {avg_score:.1f}/10).")
        elif avg_score >= 4: parts.append(f"Desempenho geral regular (score {avg_score:.1f}/10).")
        else: parts.append(f"Desempenho geral abaixo do esperado (score {avg_score:.1f}/10).")

        if len(per_file) > 1:
            scores = {name: a["score"] for name, a in per_file.items()}
            best = max(scores.items(), key=lambda x: x[1])
            worst = min(scores.items(), key=lambda x: x[1])
            parts.append(f"Melhor desempenho: '{best[0]}' ({best[1]:.1f}/10). "
                         f"Ponto de atenção: '{worst[0]}' ({worst[1]:.1f}/10).")
        elif len(per_file) == 1:
            name, analysis = list(per_file.items())[0]
            parts.append(f"Score do arquivo: {analysis['score']:.1f}/10.")
            if analysis["strengths"]:
                parts.append(f"Principais forças: {'; '.join(analysis['strengths'][:2])}.")
            if analysis["weaknesses"]:
                parts.append(f"Principais fragilidades: {'; '.join(analysis['weaknesses'][:2])}.")

        return " ".join(parts)

    # -------------- EMPTY --------------

    @staticmethod
    def _empty_analysis():
        return {
            "success": False,
            "executive_score": {
                "saude_financeira": 5.0, "eficiencia": 5.0,
                "controle_custos": 5.0, "crescimento": 5.0,
                "nivel_risco": "Moderado", "nota_geral": 5.0,
            },
            "executive_summary": "Análise indisponível.",
            "comparison": {},
            "trend": {
                "direction": "estavel", "strength": 0.5, "confidence": 0.5,
                "description": "Sem dados.", "key_observations": [],
            },
            "recommendations": [],
            "forecast": "Sem dados suficientes para previsão.",
            "conclusion": "Análise não pôde ser concluída.",
            "combined_insights": [],
            "per_file_analysis": {},
            "model_used": "intelligent_fallback_v7",
            "tokens_used": 0, "response_time_ms": 0,
            "fallback_used": True,
            "full_analysis": "Análise indisponível.",
        }