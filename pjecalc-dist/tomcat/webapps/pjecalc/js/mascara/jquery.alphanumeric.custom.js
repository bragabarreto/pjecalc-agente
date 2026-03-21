/*
 * Comportamento:
 * 
 * Para o firefox todas as funcionalidades est„o implementadas corretamente:
 * ctrl + v, colar do mouse e convers„o de caracteres especiais no meio do texto e 
 * movimentaÁ„o pelo teclado.
 * 
 * Para o IE, textos adicionados com colar do mouse e caracteres especiais
 * no meio do texto s„o convertidos apenas no onBlur.
 * 
 * ObservaÁ„o: Ctrl + V digitado rapidamente n„o È captado.
 * 
 * Parametros:
 * Allow: Caracteres que dever„o ser permitidos.
 * Converter [true, false]: True para converter acentos e Á; False para n„o converter.
 * 
 */

(function($) {

	$.fn.masktextnumeric = function(p) {

		p = $.extend(
						{
							permitidos : "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVXYWZ 0123456789",
							especiais  : "[/?.,:;-<>]",
						    allow      : "",
						    converter  : true
						}, p);

		return this.each(function() {

			var acentos  = "¡…Õ”⁄¿»Ã“Ÿ¬ Œ‘€ƒÀœ÷‹√’«›·ÈÌÛ˙‡ËÏÚ˘‚ÍÓÙ˚‰ÎÔˆ¸„ıÁ˝";
			//var traducao = "AEIOUAEIOUAEIOUAEIOUAOCYaeiouaeiouaeiouaeiouaocy";
			var traducao = "AEIOUAEIOUAEIOUAEIOUAOCYaeiouaeiouaeiouaeiouaocy";
			
			var ch = p.permitidos + p.especiais + p.allow + acentos;
			
			$(this).keypress(function(e) {
				
					if (!e.charCode) {
						k = String.fromCharCode(e.which);
					} else {
						k = String.fromCharCode(e.charCode);
					}
					
					// Verifica se o que foi digitado n„o est· na lista de
					// permitidos
					// e.charCode = 0: Backspace, <-, ->, shift + home, shift + end
					// e.charCode = 32, e.which = 32: EspaÁo
					// alert('k: '+k);
					if ($.browser.msie) {
						if (ch.indexOf(k) == -1 && e.charCode != 0
								&& e.which != 32) {
							e.preventDefault();
						}
					} else if ($.browser.mozilla){
						if (ch.indexOf(k) == -1 && e.charCode != 0
								&& e.charCode != 32) {
							e.preventDefault();
						}
					}
					
					//Enter
					if (e.keyCode == 13) {
						this.value = this.value.toUpperCase();
					}
			}

			);
			
			$(this).keyup(function(e) {
				
				var cod=e.which;

				// cod = 86: v
				if (e.ctrlKey && cod==86) {
					
					this.value = ajustaTextoPermitido(this.value);

				}
				
			});

			//IE
			$(this).blur(function (e){
				
				this.value = ajustaTextoPermitido(this.value);
				this.value = this.value.toUpperCase();
				
			})
			
			//Firefox
			$(this).bind('input', function (e){
				
				var posit = this.selectionStart;
				
				this.value = ajustaTextoPermitido(this.value);
				
				this.selectionStart=posit;
				this.selectionEnd=posit;
				this.focus();
				
			});
			
			//Percorre o texto e converte caracteres especiais
			function ajustaTextoPermitido(campo) {

				var posic, carac;
				var tempTexto = "";
				
				for (var i=0; i < campo.length; i++) {
					carac = campo.charAt(i);
					//carac = campo.toUpperCase().charAt (i); 
					posic = acentos.indexOf(carac);
					var tempCaracter = "";
					if (posic > -1 && p.converter){
						tempCaracter = traducao.charAt(posic);
					} else {
				      	tempCaracter = campo.charAt(i);
						//tempCaracter = campo.toUpperCase().charAt(i);
					}
					
					if (ch.indexOf(tempCaracter) > -1 && tempCaracter!= "") {
						tempTexto += tempCaracter;
					}	
				}
				campo = tempTexto;
				return campo;
			}


			});

	};
	
	$.fn.masktextnumericcustom = function(p) {

		p = $.extend(
						{
							permitidos : "0123456789",
							especiais  : ",",
						    allow      : "",
						    converter  : true
						}, p);

		return this.each(function() {

			var acentos  = "¡…Õ”⁄¿»Ã“Ÿ¬ Œ‘€ƒÀœ÷‹√’«›·ÈÌÛ˙‡ËÏÚ˘‚ÍÓÙ˚‰ÎÔˆ¸„ıÁ˝";
			//var traducao = "AEIOUAEIOUAEIOUAEIOUAOCYaeiouaeiouaeiouaeiouaocy";
			var traducao = "AEIOUAEIOUAEIOUAEIOUAOCYaeiouaeiouaeiouaeiouaocy";
			
			var ch = p.permitidos + p.especiais + p.allow + acentos;
			
			$(this).keypress(function(e) {
				
					if (!e.charCode) {
						k = String.fromCharCode(e.which);
					} else {
						k = String.fromCharCode(e.charCode);
					}
					
					// Verifica se o que foi digitado n„o est· na lista de
					// permitidos
					// e.charCode = 0: Backspace, <-, ->, shift + home, shift + end
					// e.charCode = 32, e.which = 32: EspaÁo
					// alert('k: '+k);
					if ($.browser.msie) {
						if (ch.indexOf(k) == -1 && e.charCode != 0
								&& e.which != 32) {
							e.preventDefault();
						}
					} else if ($.browser.mozilla){
						if (ch.indexOf(k) == -1 && e.charCode != 0
								&& e.charCode != 32) {
							e.preventDefault();
						}
					}
					
					//Enter
					if (e.keyCode == 13) {
						this.value = this.value.toUpperCase();
					}
			}

			);
			
			$(this).keyup(function(e) {
				
				var cod=e.which;

				// cod = 86: v
				if (e.ctrlKey && cod==86) {
					
					this.value = ajustaTextoPermitido(this.value);

				}
				
			});

			//IE
			$(this).blur(function (e){
				
				this.value = ajustaTextoPermitido(this.value);
				this.value = this.value.toUpperCase();
				
			})
			
			//Firefox
			$(this).bind('input', function (e){
				
				var posit = this.selectionStart;
				
				this.value = ajustaTextoPermitido(this.value);
				
				this.selectionStart=posit;
				this.selectionEnd=posit;
				this.focus();
				
			});
			
			//Percorre o texto e converte caracteres especiais
			function ajustaTextoPermitido(campo) {

				var posic, carac;
				var tempTexto = "";
				
				for (var i=0; i < campo.length; i++) {
					carac = campo.charAt(i);
					//carac = campo.toUpperCase().charAt (i); 
					posic = acentos.indexOf(carac);
					var tempCaracter = "";
					if (posic > -1 && p.converter){
						tempCaracter = traducao.charAt(posic);
					} else {
				      	tempCaracter = campo.charAt(i);
						//tempCaracter = campo.toUpperCase().charAt(i);
					}
					
					if (ch.indexOf(tempCaracter) > -1 && tempCaracter!= "") {
						tempTexto += tempCaracter;
					}	
				}
				campo = tempTexto;
				return campo;
			}


			});

	};
	
	$.fn.masktext = function(p) {

		p = $.extend({
			permitidos : "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVXYWZ "
		  }, p);	

		return this.each (function()
			{
				$(this).masktextnumeric(p);
			}
		);
			
	};
	
	$.fn.masktextcomma = function(p) {

		p = $.extend({
			permitidos : "1234567890,"
		  }, p);	

		return this.each (function()
			{
				$(this).masktextnumericcustom(p);
			}
		);
			
	};

})(jQuery);
