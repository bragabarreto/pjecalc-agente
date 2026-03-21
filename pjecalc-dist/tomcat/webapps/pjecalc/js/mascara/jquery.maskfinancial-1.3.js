/*
* Author: Ernani Jacob / Kaio Valente
* Version: 1.3
* Release: 2010-12-11
* 
*/
(function($) {
	$.fn.maskFinancial = function(p) {
		p = $.extend({
			max: "26",
			dec: "2",
			finan: true,
			menos: false
		}, p);
		
		return this.each(function(){
			
			var input=$(this);
			var dif = 0;
			var tamResult = 0;
			var flag = false;
			
			input.bind("blur", function(e) {
				evento(e);
				var retorno = input.val();
				
				if (retorno == '-0,0') {
					input.val('0,0');
					flag = false;
				}
				
			});
			input.bind("keyup",evento);
				
			function evento(e){
				tecla=e||window.event;
				
				var cod=tecla.charCode||tecla.keyCode||tecla.which;
				
				var entrada = input.val();
				
				// '-'
				if (cod == '109') {
					flag = true;
				} 
				//Backspace e delete
				if (cod == '8' || cod == '46') {
					if (entrada.indexOf('-')) {
						flag = false;
					}
				}
				// '+'
				if (cod == '107') {
					flag = false;
				}
				
				entrada = entrada.replace('-','');
				
				valor = ajustarValor(entrada);
				
				if ( !p.finan ){
					input.val(valor);
				} else {
					if (p.max <=6 ){
						valor = valor.substr(0,p.max-1);		
					}else{
						if (p.max <= 10 ){
							valor = valor.substr(0,p.max-2);		
						}else{
							if (p.max <= 14 ){
								valor = valor.substr(0,p.max-3);		
							}else{
								if (p.max <= 18 ){
									valor = valor.substr(0,p.max-4);		
								}else{
									if (p.max >= 19 ){
										valor = valor.substr(0,p.max-4);
									}		
								}
							}
						}
					}
					var posit  = this.selectionStart;
					
					var newPosit = posit;
					
					if (flag) {
						newPosit = posit-1;
					}
					
					var novoTam = tamResult;
					if ($.browser.mozilla) {
						novoTam = novoTam + 1;
					} 
					
					//Inserir numeros sempre no fim.
					if (newPosit < novoTam && (cod >= 96 && cod <= 105) ) {
						var val = entrada;
						var pontos = 0;
						
						for (var i=0; i<newPosit; i++) {
							if (val[i] == '.' || val[i] == ',')
								pontos++;
						}
						
						var posicao = newPosit-pontos;

						var numero = valor.substring(posicao-1, posicao);
						
						var pre = valor.substring(0,posicao-1);
						var pos = valor.substring(posicao);
						
						if (numero == '') {
							numero = valor.substring(posicao, posicao+1);
							pre = valor.substring(0,posicao);
							pos = valor.substring(posicao+1);
						}
						
						valor = pre+pos+numero;
					}
					var result = '';
					
					//Tratamento para aceitar 0
					if (valor == '0' && valor.length == '1') {
						if (e.which != '96')
							result = maskValue(valor, valor.length);
						else
							result = '0,0';
					} else {
						result = maskValue(valor, valor.length);
					}
					
					var cursor = 0;
					
					if ( flag && result.indexOf('-') && p.menos ) {
						result = '-'+result;
					}
					
					if (result.substring(0,2) == '-.') {
						result = '-'+result.substring(2);
					}
					input.val(result);
					
					cursor = tratarEvento(e, posit, result, valor);

					if (cod != 16 && cod != 9 && cod != 13 && cod != 0 &&  cod != 35 && cod != 36 && cod != 37 && cod != 39 ) {
						this.selectionStart=cursor;
						this.selectionEnd=cursor;
						this.focus();	
					}
				}
			}
			
			function tratarEvento(e, posit, result, valor) {
				var cursor = posit;
				//backspace 
				if (e.which == '8') {
					if ( valor.length == 2 && result.length == tamResult) {
						cursor = posit+1;
					}
					else if ((tamResult - result.length) == 2 ) {
						cursor = posit - 1;
					} 
				}
				//delete
				else if (e.which == '46') {
					
					if ((result.length == tamResult)) {
						cursor = posit+1;
					}
					else if ((tamResult - result.length) == 2 ) {
						cursor = posit - 1;
					} 
						
				}
				else if (e.ctrlKey && e.which == 86) {
					if ((result.length - tamResult) > 2) {
						cursor = posit + 1;
					} 
				}
				else { 				
					cursor = result.length;
				}
				tamResult = result.length;
				
				return cursor;
				
			}
			
			function ajustarValor(v) {
				var valor_limpo = '';
				var contador;
				for (var i=0; i < v.length; i++) {
					contador = '0123456789'.indexOf(v.substring(i, i+1));
					if (contador >= 0) {
						valor_limpo += contador;
					}
					// Parametrizar valor negativo
					if (i == 0) {
						if ( v.substring(0,1) == '-' ){
							valor_limpo += '-';
						}
					}
					
				}
				return valor_limpo;
			}
			
			function maskValue(vr, tam) {
				var result = vr;
				if ( tam <= p.dec ) { 
					if (tam == 1) {
						result = '0,';
						for (var i=1; i<=p.dec-1; i++) {
							result += '0';
						}
							
						result += vr;
					}
					
					if (tam > 1 && vr.substring(0,1) != '0' ) {
						result = '0,';
						for (var i=1; i<=p.dec-tam; i++) {
							result += '0';
						}
						
						result += vr;
					} 
					else if (tam == p.dec && vr.substring(0,1) == '0' ) {
						result = '0,';
						
						result += vr;
					}
					
					if (vr == '00') {
						result = '0,0';
					}
					
					if (vr == '0') {
						flag = false;
						result = '';
					}
				
 					return result;
 				} else {
				
					if (vr.substring(0,2) == '00') {
						var sub = vr.substring(2);
						if (sub.length > 1)
							result = '0,'+vr.substring(2);
						else
							result = '0,0'+vr.substring(2);
						return result;
					} 
					
					else if ((tam == 3) && vr.substring(0,1) == '0' ) {
						result = '0,';
						
						result += vr.substring(1);
						return result;
					}
					
 				}
 				
				if ( (tam > p.dec) && (tam <= 5) ) {
					if (vr.substring(0,1) == '0') {
						result = vr.substr( 1, tam - p.dec - 1 ) + "," + vr.substr( tam - p.dec, tam ) ;
					} else {
						result = vr.substr( 0, tam - p.dec ) + "," + vr.substr( tam - p.dec, tam ) ;
					}
					return result; 
				}
				if ( (p.max >= p.dec) && (p.max <= 5) ){
					vr = vr.substr(0,p.max);
					tam = vr.length;
					result = vr.substr( 0, tam - p.dec ) + "," + vr.substr( tam - p.dec, tam ) ;
					return result;					
				}
				
				if ( (tam >= 6) && (tam <= 8) ){ 
					result = vr.substr( 0, tam - 5 ) + "." + vr.substr( tam - 5, 3 ) + "," + vr.substr( tam - p.dec, tam ) ;
					return result; 
				}
				if ( (p.max >= 6) && (p.max <= 8) ){
					vr = vr.substr(0,p.max);
					tam = vr.length;
					result = vr.substr( 0, tam - 5 ) + "." + vr.substr( tam - 5, 3 ) + "," + vr.substr( tam - p.dec, tam ) ;
					return result; 
				}
				
				if ( (tam >= 9) && (tam <= 11) ){
					result = vr.substr( 0, tam - 8 ) + "." + vr.substr( tam - 8, 3 ) + "." + vr.substr( tam - 5, 3 ) + "," + vr.substr( tam - p.dec, tam ) ;
					return result; 
				}
				if ( (p.max >= 9) && (p.max <= 11) ){
					vr = vr.substr(0,p.max);
					tam = vr.length;
					result = vr.substr( 0, tam - 8 ) + "." + vr.substr( tam - 8, 3 ) + "." + vr.substr( tam - 5, 3 ) + "," + vr.substr( tam - p.dec, tam ) ;
					return result; 
				}
				
				if ( (tam >= 12) && (tam <= 14) ){
					result = vr.substr( 0, tam - 11 ) + "." + vr.substr( tam - 11, 3 ) + "." + vr.substr( tam - 8, 3 ) + "." + vr.substr( tam - 5, 3 ) + "," + vr.substr( tam - p.dec, tam ) ;
  				    return result;
				}
				if ( (p.max >= 12) && (p.max <= 14) ){
					vr = vr.substr(0,p.max);
					tam = vr.length;
					result = vr.substr( 0, tam - 11 ) + "." + vr.substr( tam - 11, 3 ) + "." + vr.substr( tam - 8, 3 ) + "." + vr.substr( tam - 5, 3 ) + "," + vr.substr( tam - p.dec, tam ) ;
  				    return result;
				}
				
				if ( (tam >= 15) && (tam <= 17) ){
					result = vr.substr( 0, tam - 14 ) + "." + vr.substr( tam - 14, 3 ) + "." + vr.substr( tam - 11, 3 ) + "." + vr.substr( tam - 8, 3 ) + "." + vr.substr( tam - 5, 3 ) + "," + vr.substr( tam - p.dec, tam ) ;
					return result;
				}
				if ( (p.max >= 15) && (p.max <= 17) ){
					vr = vr.substr(0,p.max);
					tam = vr.length;
					result = vr.substr( 0, tam - 14 ) + "." + vr.substr( tam - 14, 3 ) + "." + vr.substr( tam - 11, 3 ) + "." + vr.substr( tam - 8, 3 ) + "." + vr.substr( tam - 5, 3 ) + "," + vr.substr( tam - p.dec, tam ) ;
					return result;
				}
				
				if ( (tam >= 18) && (tam <= 20) ){
					result = vr.substr( 0, tam - 17 ) + "." + vr.substr( tam - 17, 3 ) + "." + vr.substr( tam - 14, 3 ) + "." + vr.substr( tam - 11, 3 ) + "." + vr.substr( tam - 8, 3 ) + "." + vr.substr( tam - 5, 3 ) + "," + vr.substr( tam - p.dec, tam ) ;
					return result;
				}
				if ( (p.max >= 18) && (p.max <= 20) ){
					vr = vr.substr(0,p.max);
					tam = vr.length;
					result = vr.substr( 0, tam - 17 ) + "." + vr.substr( tam - 17, 3 ) + "." + vr.substr( tam - 14, 3 ) + "." + vr.substr( tam - 11, 3 ) + "." + vr.substr( tam - 8, 3 ) + "." + vr.substr( tam - 5, 3 ) + "," + vr.substr( tam - p.dec, tam ) ;
					return result;
				}
				
				if ( tam >= 21 ){
					vr = vr.substr(0,20);
					tam = vr.length;
					result = vr.substr( 0, tam - 17 ) + "." + vr.substr( tam - 17, 3 ) + "." + vr.substr( tam - 14, 3 ) + "." + vr.substr( tam - 11, 3 ) + "." + vr.substr( tam - 8, 3 ) + "." + vr.substr( tam - 5, 3 ) + "," + vr.substr( tam - p.dec, tam ) ;
				}
				return result;
			}
			
			input.one("unmaskFinancial",function(){
				input.unbind("blur",evento);
				input.unbind("keyup",evento);
				input.unbind("input",evento);
				if ($.browser.msie)
					this.onpaste=null;
				else if ($.browser.mozilla)
						this.removeEventListener('input',evento,false);
			});
		});
	}
	
	$.fn.maskNumeric = function(p) {

		p = $.extend({
			max: "26",
			finan: false
		  }, p);	

		return this.each (function()
			{
				$(this).maskFinancial(p);
			}
		);
			
	};
	
	$.fn.unmaskFinancial=function(){
		return this.trigger("unmaskFinancial");
	};
})(jQuery);