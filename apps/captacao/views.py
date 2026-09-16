from django.contrib import messages
from django.db.models import Count
from django.shortcuts import redirect, render

from apps.captacao.models import PrecoCaptado, Rede


def concorrentes(request):
    """Configuração de Concorrentes -- Gabriel pediu (16/09/26) pra ver
    TODO estabelecimento captado (não só os curados originais) e marcar/
    desmarcar quem conta como concorrente de verdade no Monitor de Preço
    ("não existe isso de curado"). Cada Rede tipo=concorrente tem um
    `ativa` que decide se entra na comparação -- as descobertas
    automaticamente (`manage.py descobrir_concorrentes`) começam
    inativas até serem revisadas aqui."""
    if request.method == "POST":
        ids_ativos = set(request.POST.getlist("ativa"))
        redes = list(Rede.objects.filter(tipo=Rede.TIPO_CONCORRENTE))
        for r in redes:
            nova_ativa = str(r.id) in ids_ativos
            if nova_ativa != r.ativa:
                r.ativa = nova_ativa
                r.save(update_fields=["ativa"])
        messages.success(request, "Concorrentes atualizados.")
        return redirect("captacao:concorrentes")

    redes = (
        Rede.objects.filter(tipo=Rede.TIPO_CONCORRENTE)
        .annotate(n_registros=Count("precos"))
        .order_by("-ativa", "-n_registros", "nome")
    )
    context = {
        "redes": redes,
        "n_ativas": sum(1 for r in redes if r.ativa),
        "n_total": len(redes),
    }
    return render(request, "captacao/concorrentes.html", context)
