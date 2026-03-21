(function($){

	$.fn.alphanumeric = function(p) { 

		p = $.extend({
			//ichars: "!@#$%^&*()+=[]\\\';,/{}|\":<>?~`.- ",
			ichars: "!@#$%^&*()+=[]\\\';,/{}|\":<>?~`.- _ ´¨§¹²³£¢¬ªºÁÉÍÓÚÀÈÌÒÙÂÊÔÄËÏÖÜÃÕáéíóúàèìòùâêîôûäëïöüãõçÇıİ",
			nchars: "",
			allow: ""
		  }, p);	

		return this.each
			(
				function() 
				{

					if (p.nocaps) p.nchars += "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
					if (p.allcaps) p.nchars += "abcdefghijklmnopqrstuvwxyz";
					
					s = p.allow.split('');
					for ( i=0;i<s.length;i++) if (p.ichars.indexOf(s[i]) != -1) s[i] = "\\" + s[i];
					p.allow = s.join('|');
					
					var reg = new RegExp(p.allow,'gi');
					var ch = p.ichars + p.nchars;
					ch = ch.replace(reg,'');

					$(this).keypress
						(
							function (e)
								{
								
									if (!e.charCode) k = String.fromCharCode(e.which);
										else k = String.fromCharCode(e.charCode);
										
									if (ch.indexOf(k) != -1) e.preventDefault();
									//if (e.ctrlKey&&k=='v') e.preventDefault();
									
								}
								
						);
					
					//Tratamento para copiar e colar (teclado e mouse)
					$(this).bind("input",ajustaTextoNumerico);
					$(this).bind("blur",ajustaTextoNumerico);
					$(this).bind("keyup",ajustaTextoNumerico);
					
					
					//Percorre o texto e converte caracteres especiais
					function ajustaTextoNumerico() {

						var posic, carac;
						var tempTexto = "";
						var numeros = "0123456789";
						var campo = this.value;
						
						for (var i=0; i < campo.length; i++) {
							carac = campo.charAt(i);
							posic = numeros.indexOf(carac);
							if (posic > -1){
								tempTexto += carac;
							}
							
						}
						campo = tempTexto;
						
						jQuery(this).val(campo);
					}
									
				}
			);

	};

	$.fn.numeric = function(p) {
	
		var az = "abcdefghijklmnopqrstuvwxyz";
		az += az.toUpperCase();

		p = $.extend({
			nchars: az
		  }, p);	
		  	
		return this.each (function()
			{
				$(this).alphanumeric(p);
			}
		);
			
	};
	
	$.fn.alpha = function(p) {

		var nm = "1234567890";

		p = $.extend({
			nchars: nm
		  }, p);	

		return this.each (function()
			{
				$(this).alphanumeric(p);
			}
		);
			
	};	

})(jQuery);
