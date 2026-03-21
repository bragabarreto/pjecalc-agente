var nomes = new Array();
var links = new Array();
var redirecionando = false;
var indice_tabindex_menu = 1004;
var indice_tabindex_login = indice_tabindex_menu - 1;
var indice_tabindex_logout = indice_tabindex_menu + 500;

function criarLinkAcessivel(id_item, cor) {
	indice_tabindex_menu++;
	
	var id_item_menu = String(id_item).replace('\\:', ':');
	var id_item_menu_jquery = id_item_menu.replace(':', '\\:'); // precisa escapar no jquery, no prototype nao
	
	var id_link_criado = "_" + indice_tabindex_menu + "_" + id_item_menu.replace(':', '');
	
	jQuery("#" + id_item_menu_jquery + '_span').wrapInner("<a id='" + id_link_criado + "' href='#' tabindex='" + indice_tabindex_menu + "' style='color:" + cor + " !important' />");
	jQuery("#" + id_item_menu_jquery + '\\:anchor').wrapInner("<a id='" + id_link_criado + "' href='#' tabindex='" + indice_tabindex_menu + "' style='color:" + cor + " !important' />");
	
	simularMouseNoLink(id_link_criado);
}

function buscarItensDeMenu() {
	nomes = [];
	links = [];
	
	// Busca TODOS os itens disponÃ­veis no menu.
	
	jQuery('#menupainel > li.header').each(
		function(index, value) {
			var texto_menu = jQuery(this).text();
			
			jQuery(jQuery(this).parent().children('li.menu-item')[index]).find('li').each(
					function(index2, value2) {
						var texto_sub_menu = jQuery(this).text();
						nomes.push(texto_menu + ' > ' + texto_sub_menu);
						links.push(jQuery(this).find('a'));
					}
			);
		}
	);
	
	
}

function simularMouseNoLink(id_link_criado) {
	// ao focus -> simular mouseover
	jQuery(id_link_criado).observe("focus", function (event) {
	  var element = event.element();
	  jQuery(element).up().simulate('mouseover');
	});
	// ao blur -> simular mouseout
	jQuery(id_link_criado).observe("blur", function (event) {
	  var element = event.element();
	  jQuery(element).up().simulate('mouseout');
	});
}

function criarLinkAcessivelLoginLogout() {
	try {
		var linksLoginOut = jQuery('.rich-toolbar-item > a');
		var linkLogin = jQuery(linksLoginOut.get(0));
		var linkLogout = jQuery(linksLoginOut.get(1));
		
		linkLogin.attr('tabindex', indice_tabindex_login);
		linkLogin.attr('accesskey', '1');
		linkLogin.attr('alt', 'Atalho: alt + 1 ou alt + shift + 1');
		simularMouseNoLink(linkLogin.attr('id'));
		
		linkLogout.attr('tabindex', indice_tabindex_logout);
		linkLogout.attr('accesskey', '9');
		linkLogout.attr('alt', 'Atalho: alt + 9 ou alt + shift + 9');
		simularMouseNoLink(linkLogout.attr('id'));
	} catch (err) {
	}
}

function criarTitleIndicativoSubMenu(id_item) {
	var id_item_menu = String(id_item).replace('\\:', ':');
	var id_item_menu_jquery = id_item_menu.replace(':', '\\:'); // precisa escapar no jquery, no prototype nao
	
	jQuery("#" + id_item_menu_jquery + '_span a:last').append("<span class='acessibilidade'>Possui submenu</span>");
	jQuery("#" + id_item_menu_jquery + '\\:anchor a:last').append("<span class='acessibilidade'>Possui submenu</span>");
	
}

function criarTitleIndicativoUltimoLista(id_item) {
	var id_item_menu = String(id_item).replace('\\:', ':');
	var id_item_menu_jquery = id_item_menu.replace(':', '\\:'); // precisa escapar no jquery, no prototype nao
	
	jQuery("#" + id_item_menu_jquery + '_span a:last').append("<span class='acessibilidade'>ï¿½ltimo da lista</span>");
	jQuery("#" + id_item_menu_jquery + '\\:anchor a:last').append("<span class='acessibilidade'>ï¿½ltimo da lista</span>");
	
}

// Esse cÃ³digo Ã© aproveitado do PJe. NÃ£o se aplica ao PJe-Calc.
jQuery(document).ready(
		function() {
			try {
				criarLinkAcessivelLoginLogout();
				
				jQuery('.rich-ddmenu-label > .rich-label-text-decor') // retorna todos menus principais (raizes)
					.each(
						// para cada item de menu, percorrer recursivamente os filhos, 
						// parando somente ao encontrar itens folhas (momento em que adiciona na lista de itens de menus pesquisaveis)
						function(index, value) {
							
							var id_item_menu = String(jQuery(this).attr('id'));
							var id_item_menu_jquery = id_item_menu.replace(':', '\\:'); // precisa escapar no jquery, no prototype nao
							
							var texto_menu = jQuery(this).text();
							var id = id_item_menu_jquery.replace('_span', '');
							extrair_filhos(id, texto_menu, true, false);
						});
			} catch (err) { // evitar, caso mude o richfaces, dar erro de js
			}
		}
);

//Esse cÃ³digo Ã© aproveitado do PJe. NÃ£o se aplica ao PJe-Calc.
function extrair_filhos(id, caminho_anterior, raiz, is_ultimo_da_lista) {
	var id_script = '#' + id + '_menu_script';
	var cor = '#000000';
	if (raiz) {
		cor = corRaiz;
	}
	
	criarLinkAcessivel(id, cor);
	if (is_ultimo_da_lista) {
		criarTitleIndicativoUltimoLista(id);
	}
	
	if (jQuery(id_script).size() == 0) { // se chegou no item de menu folha, entao adiciona-lo a lista de menus
		nomes.push(caminho_anterior);
		links.push(id);
		return;
	}
	// tem submenu
	criarTitleIndicativoSubMenu(id);
	
	var matchs = jQuery(id_script).html().match(/r?\[\'.*?\'.?,?/g);
	// para cada filho, executar recursivamente a funcao
	jQuery(matchs).each(
			function(index, value) {
				var id_filho = String(value).replace("['", "").replace("',", "").replace("']", "").replace(':', '\\:');
				var text_menu = caminho_anterior + ' > ' + jQuery('#' + id_filho + '\\:anchor').text();
				
				var ultimo_da_lista = false;
				if (index == matchs.length - 1) {
					ultimo_da_lista = true;
				}

				extrair_filhos(id_filho, text_menu, false, ultimo_da_lista);
			});
}

function escondeSelectPesquisa(idSelect) {
	select = document.getElementById(idSelect);
	var i = select.selectedIndex;
	if (i = 0) {
		select.style.display = "none";
		select.size = "1";
	}
}

function autoComplete(field, select) {
	// remover todas as opï¿½ï¿½es de menu
	
	while (select.options.length > 0) {
		try {
			select.remove(0);
		} catch (err) {
		}
	}

	if (field.value != "") {

		var words = retirarAcentos(field.value).toUpperCase();
		words = words.split(" ");
		
		buscarItensDeMenu();
		
		for ( var i = 0; i < nomes.length; i++) {
			var achou = 0;
			var nomeAmigavel = retirarAcentos(nomes[i]).toUpperCase();
			for ( var w = 0; w < words.length; w++)
				if (nomeAmigavel.indexOf(words[w]) != -1)
					achou++;

			if (achou == words.length) {
				var o = document.createElement('option');
				o.text = nomes[i];
				o.value = i;
				try {
					select.add(o, null);
				} catch (err) {
					select.add(o);
				}
				select.style.display = "";
				select.size = "6";
			}
		}
	} else {
		select.style.display = "none";
		select.size = "1";
	}
	if (select.options.length == 0) {
		select.style.display = "none";
		select.size = "1";
	}
}

function limpaCampoPesquisa(campo, idSelect, evt) {
	if (!evt)
		evt = window.event;
	if (campo.value == undefined)
		campo = document.getElementById(campo);
	try {
		if (evt.explicitOriginalTarget.name == idSelect) {
			campo.focus();
			return;
		}
	} catch (err) {
	}
	if (campo.value != "") {
		select = document.getElementById(idSelect);
		select.style.display = "none";
		select.size = "1";
		campo.value = "";
	}
	campo.focus();
}

function clicarItemMenu(select) {
	if (redirecionando) {
		return;
	}
	var i = select.selectedIndex;
	if (i >= 0) {
		linkIndex = select.options[i].value;
		if (linkIndex >= 0) {
			if (links[linkIndex] != null) {
				redirecionando = true;
				links[linkIndex].click();
			}
		}
	}
}

function retirarAcentos(txt) {
	var texto = txt;
	var textoSemAcento;
	textoSemAcento = texto.replace(/ã/gi, "a");
	textoSemAcento = textoSemAcento.replace(/á/gi, "a");
	textoSemAcento = textoSemAcento.replace(/à/gi, "a");
	textoSemAcento = textoSemAcento.replace(/â/gi, "a");
	textoSemAcento = textoSemAcento.replace(/ê/gi, "e");
	textoSemAcento = textoSemAcento.replace(/é/gi, "e");
	textoSemAcento = textoSemAcento.replace(/è/gi, "e");
	textoSemAcento = textoSemAcento.replace(/í/gi, "i");
	textoSemAcento = textoSemAcento.replace(/ì/gi, "i");
	textoSemAcento = textoSemAcento.replace(/ô/gi, "o");
	textoSemAcento = textoSemAcento.replace(/ó/gi, "o");
	textoSemAcento = textoSemAcento.replace(/õ/gi, "o");
	textoSemAcento = textoSemAcento.replace(/ú/gi, "u");
	textoSemAcento = textoSemAcento.replace(/ù/gi, "u");
	textoSemAcento = textoSemAcento.replace(/ü/gi, "u");
	textoSemAcento = textoSemAcento.replace(/ç/gi, "c");
	return textoSemAcento;
}

function isResultadosPesquisaMenuVazio(idCampoSelect) {
	campoSelect = document.getElementById(idCampoSelect);
	return campoSelect.length == 0;
}

function isApertouEnter(evt) {
	if (!evt)
		evt = window.event;
	return evt.keyCode == 13;
}

function saltaParaSelect(campo, idCampoSelect, evt) {
	campoSelect = document.getElementById(idCampoSelect);
	if (!evt)
		evt = window.event;

	if ((evt.keyCode == 40 && campoSelect.length > 0) // SETA para baixo E existe itens no select
			|| (evt.keyCode == 13 && campoSelect.length > 1)) { // ENTER e ha mais de uma opcao no select
		try {
			campoSelect.focus();
		} catch (err) {
		}

		try {
			campoSelect.selectedIndex = 0;
		} catch (err) {
		}
		evt.returnValue = false;
		return false;
	} else if (evt.keyCode == 13 && campoSelect.length == 1) { // ENTER e ha uma opcao no select -> redirecionar
		try {
			campoSelect.focus();
		} catch (err) {
		}
		try {
			campoSelect.selectedIndex = 0;
		} catch (err) {
		}
		clicarItemMenu(campoSelect);
		evt.returnValue = false;
		return false;
	} else if (evt.keyCode == 13) { // ENTER e nao ha nenhuma opcao -> comportamento padrao (pesquisar)
		evt.returnValue = true;
		return true;
	} else if (evt.keyCode == 27) { // ESC -> limpar select
		campoSelect.style.display = "none";
		campoSelect.size = "1";
		campo.value = "";
		evt.returnValue = false;
		return false;
	} else {
		if (campo.value.length > 2) {
			autoComplete(campo, campoSelect);
		}
	}
	evt.returnValue = true;
	return true;
}

function pressionouTeclaNoSelect(campoSelect, evt) {
	if (!evt)
		evt = window.event;

	if (evt.keyCode == 13) // ENTER
	{
		clicarItemMenu(campoSelect);
		evt.returnValue = false;
		return false;
	} else if ((evt.keyCode == 20) && !(campoSelect.selectedIndex > 0)) {
		campoSelect.selectedIndex = 0;
		evt.returnValue = false;
		return false;
	} else if (evt.keyCode == 27) { // ESC
		limpaCampoPesquisa(jQuery("*[id$=':searchText']").get(0),
				'selAcheFacil', null);
	}
}

// funcao prototype para simular eventos

(function(){
	  
	  var eventMatchers = {
	    'HTMLEvents': /^(?:load|unload|abort|error|select|change|submit|reset|focus|blur|resize|scroll)$/,
	    'MouseEvents': /^(?:click|mouse(?:down|up|over|move|out))$/
	  }
	  var defaultOptions = {
	    pointerX: 0,
	    pointerY: 0,
	    button: 0,
	    ctrlKey: false,
	    altKey: false,
	    shiftKey: false,
	    metaKey: false,
	    bubbles: true,
	    cancelable: true
	  }
	  
	  Event.simulate = function(element, eventName) {
	    var options = Object.extend(defaultOptions, arguments[2] || { });
	    var oEvent, eventType = null;
	    
	    element = jQuery(element);
	    
	    for (var name in eventMatchers) {
	      if (eventMatchers[name].test(eventName)) { eventType = name; break; }
	    }

	    if (!eventType)
	      throw new SyntaxError('Only HTMLEvents and MouseEvents interfaces are supported');

	    if (document.createEvent) {
	      oEvent = document.createEvent(eventType);
	      if (eventType == 'HTMLEvents') {
	        oEvent.initEvent(eventName, options.bubbles, options.cancelable);
	      }
	      else {
	        oEvent.initMouseEvent(eventName, options.bubbles, options.cancelable, document.defaultView,
	          options.button, options.pointerX, options.pointerY, options.pointerX, options.pointerY,
	          options.ctrlKey, options.altKey, options.shiftKey, options.metaKey, options.button, element);
	      }
	      element.dispatchEvent(oEvent);
	    }
	    else {
	      options.clientX = options.pointerX;
	      options.clientY = options.pointerY;
	      oEvent = Object.extend(document.createEventObject(), options);
	      element.fireEvent('on' + eventName, oEvent);
	    }
	    return element;
	  }
	  
	  Element.addMethods({ simulate: Event.simulate });
	})()