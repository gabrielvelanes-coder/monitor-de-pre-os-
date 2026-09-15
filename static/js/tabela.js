// Tabelas interativas: ordenar clicando no cabeçalho + filtro instantâneo,
// sem round-trip pro servidor. Aplica em <table class="tabela-interativa">
// com <th data-ordenavel> nas colunas que fazem sentido ordenar.
//
// Cuidado especial (diferente de um padrão genérico): o Monitor de Preço
// tem uma <tr class="linha-detalhe"> opcional logo depois de cada linha
// normal (o painel "ver detalhes" com nossas lojas x concorrentes) --
// ordenar/filtrar precisa mover/esconder o par junto, senão o painel
// expandido fica órfão, grudado na linha errada.
(function () {
  function valorNumerico(texto) {
    // "R$ 1.234,56" / "1.234" / "12,3%" / "há 4 dias" -> número, ou null.
    var limpo = texto.replace(/[^0-9,.\-]/g, '').trim();
    if (!limpo) return null;
    limpo = limpo.replace(/\./g, '').replace(',', '.');
    var n = parseFloat(limpo);
    return isNaN(n) ? null : n;
  }

  function agruparLinhas(tbody) {
    var grupos = [];
    var linhas = Array.prototype.slice.call(tbody.rows);
    for (var i = 0; i < linhas.length; i++) {
      if (linhas[i].classList.contains('linha-detalhe')) continue;
      var grupo = [linhas[i]];
      if (linhas[i + 1] && linhas[i + 1].classList.contains('linha-detalhe')) {
        grupo.push(linhas[i + 1]);
        i++;
      }
      grupos.push(grupo);
    }
    return grupos;
  }

  function ordenarTabela(tabela, indiceColuna, asc) {
    var tbody = tabela.tBodies[0];
    var grupos = agruparLinhas(tbody);
    var numerica = grupos.every(function (g) {
      var celula = g[0].cells[indiceColuna];
      return !celula || celula.textContent.trim() === '' || valorNumerico(celula.textContent) !== null;
    });

    grupos.sort(function (ga, gb) {
      var ta = ga[0].cells[indiceColuna] ? ga[0].cells[indiceColuna].textContent.trim() : '';
      var tb = gb[0].cells[indiceColuna] ? gb[0].cells[indiceColuna].textContent.trim() : '';
      var va = numerica ? (valorNumerico(ta) || 0) : ta.toLowerCase();
      var vb = numerica ? (valorNumerico(tb) || 0) : tb.toLowerCase();
      if (va < vb) return asc ? -1 : 1;
      if (va > vb) return asc ? 1 : -1;
      return 0;
    });

    grupos.forEach(function (g) {
      g.forEach(function (linha) { tbody.appendChild(linha); });
    });
  }

  function iniciarOrdenacao() {
    document.querySelectorAll('table.tabela-interativa').forEach(function (tabela) {
      var cabecalhos = tabela.tHead ? tabela.tHead.rows[0].cells : [];
      Array.prototype.forEach.call(cabecalhos, function (th, indice) {
        if (!('ordenavel' in th.dataset)) return;
        th.classList.add('th-ordenavel');
        th.dataset.ordemAsc = 'true';
        th.addEventListener('click', function () {
          var asc = th.dataset.ordemAsc === 'true';
          Array.prototype.forEach.call(cabecalhos, function (outro) {
            outro.classList.remove('ordenado-asc', 'ordenado-desc');
          });
          th.classList.add(asc ? 'ordenado-asc' : 'ordenado-desc');
          ordenarTabela(tabela, indice, asc);
          th.dataset.ordemAsc = asc ? 'false' : 'true';
        });
      });
    });
  }

  function iniciarFiltro() {
    document.querySelectorAll('[data-filtro-tabela]').forEach(function (input) {
      var tabela = document.getElementById(input.dataset.filtroTabela);
      if (!tabela) return;
      input.addEventListener('input', function () {
        var termo = input.value.trim().toLowerCase();
        var oculta = false;
        Array.prototype.forEach.call(tabela.tBodies[0].rows, function (linha) {
          if (linha.classList.contains('linha-detalhe')) {
            linha.hidden = oculta;
            return;
          }
          oculta = termo !== '' && linha.textContent.toLowerCase().indexOf(termo) === -1;
          linha.hidden = oculta;
        });
      });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    iniciarOrdenacao();
    iniciarFiltro();
  });
})();
