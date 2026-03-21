/**
 * Plugin jQuery de suporte com v�rios m�todos importantes para m�scaras (CPF, CNPJ e Data), autocomplete, etc.
 * Autor: Raimundo Botelho
 * Data: 01/03/2010
 * Email: raimundo.botelho@gmail.com
 */
var UtilsMethods = {

    numberMask: function(input){
        if (!input.readAttribute('masked')) {
            input.style.textAlign='right';
            input.maxLength=10;
            jQuery(input).maskMoney({decimal:",", thousands:".", allowZero:true});
            input.writeAttribute('masked',true);
        }
    },

    unmask: function(input) {
        if (input.readAttribute('masked')) {
            jQuery(input).unmask();
            input.removeAttribute('masked');
        }
    },
    
    dateMask: function(input){
        if (!input.readAttribute('masked')) {
            input.maxLength=10;
            input.setMask("99/99/9999");
            input.writeAttribute('masked',true);
        }
    },
    
    dateMaskDayAndMonth: function(input){
        if (!input.readAttribute('masked')) {
            input.maxLength=10;
            input.setMask("99/99");
            input.writeAttribute('masked',true);
        }
    },
    
    autoComplete: function(input,url,extra){
    	jqInput = jQuery(input);
    	jqInput.autocomplete(url,{onItemSelect: function (item) {
    		if (extra) {
    			jQuery(extra).val(item.extra);
    		}
    		jqInput.focus();
    	}});
    },

    monthYearMask: function(input){
        if (!input.readAttribute('masked')) {
            input.maxLength=7;
            input.setMask("99/9999");
            input.writeAttribute('masked',true);
        }
    },

    timeMask: function(input){
        if (!input.readAttribute('masked')) {
            input.setMask("99:99");
            input.writeAttribute('masked',true);
        }
    },

    timeAllMask: function(input){
        if (!input.readAttribute('masked')) {
            input.maxLength=8;
            input.setMask("99:99:99");
            input.writeAttribute('masked',true);
        }
    },
    
    dynamicMask: function(input,selectorId){
    	type = '';
    	for (var i=0; i<6; i++) {
    		elem = $(selectorId+":"+i);
    		if (elem == null) {
    			break;
    		}
    		if (elem.checked) {
    			type = elem.value;
    			break;
    		}
    	}
    	if (type != '') {
    		input.unmask();
    	}
    	if (type == 'CPF') {
    		input.cpfMask();
    	}
    	else if (type == 'CNPJ') {
    		input.cnpjMask();
    	}
    	else if (type == 'CEI') {
    		input.ceiMask();
    	}
    	else if (type == 'PIS' || type == 'PASEP' || type == 'NIT') {
    		input.pisPasepNitMask();
    	}
    },
    
    leftPad: function(input,chr,size){
    	if (input.value.length > 0){
    		while (input.value.length < size) {
    			input.value = chr + input.value;
    		}
    	}
    },
    
    cpfMask: function(input){
        if (!input.readAttribute('masked')) {
            input.maxLength=14;
            input.setMask("999.999.999-99");
            input.writeAttribute('masked',true);
        }
    },

    cnpjMask: function(input){
        if (!input.readAttribute('masked')) {
            input.maxLength=18;
            input.setMask("99.999.999/9999-99");
            input.writeAttribute('masked',true);
        }
    },

    pisPasepNitMask: function(input){
        if (!input.readAttribute('masked')) {
            input.maxLength=18;
            input.setMask("999.99999.99-9");
            input.writeAttribute('masked',true);
        }
    },

    ceiMask: function(input){
        if (!input.readAttribute('masked')) {
            input.maxLength=18;
            input.setMask("99.999.99999/99");
            input.writeAttribute('masked',true);
        }
    },

    cepMask: function(input){
        if (!input.readAttribute('masked')) {
            input.maxLength=9;
            input.setMask("99999-999");
            input.writeAttribute('masked',true);
        }
    },

    dddTelefoneMask: function(input){
        if (!input.readAttribute('masked')) {
            input.maxLength=14;
            input.setMask("(99) 9999-9999");
            input.writeAttribute('masked',true);
        }
    },
    
    telefoneMask: function(input){
        if (!input.readAttribute('masked')) {
            input.maxLength=9;
            input.setMask("9999-9999");
            input.writeAttribute('masked',true);
        }
    },

    setMask: function(input, mask) {
        jqInput = jQuery(input);
        jqInput.mask(mask);
        jqInput.focus();
    },
    
    integerMask: function(input){
        if (!input.readAttribute('masked')) {
        	jqInput = jQuery(input);
        	jqInput.numeric({allow:""});;
        	jqInput.writeAttribute('masked',true);
        	jqInput.focus();
        }
    },
    
    textAndNumberMask: function(input){
        if (!input.readAttribute('masked')) {
        	jqInput = jQuery(input);
        	jqInput.masktextnumeric({allow:""});
        	jqInput.writeAttribute('masked',true);
        	jqInput.focus();
        }
    },

    currencyMask: function(input){
        if (!input.readAttribute('masked')) {
        	jqInput = jQuery(input);
        	jqInput.unmaskMoney();
        	jqInput.maskMoney();
        	jqInput.addClass('right');  
        	jqInput.writeAttribute('masked',true);
        	jqInput.maxLength=16; 
        	jqInput.focus();
        }
    },
    
    decimalMask: function(input,precision){
        if (!input.readAttribute('masked')) {
        	jqInput = jQuery(input);
        	jqInput.unmaskMoney();
        	jqInput.maskMoney({precision: precision});
        	jqInput.addClass('right');  
        	jqInput.writeAttribute('masked',true);
        	jqInput.focus();
        }
    },
    
    decimalMaskAllowNegative: function(input,precision){
        if (!input.readAttribute('masked')) {
        	jqInput = jQuery(input);
        	jqInput.unmaskMoney();
        	jqInput.maskMoney({precision: precision, allowNegative:true});
        	jqInput.addClass('right');  
        	jqInput.writeAttribute('masked',true);
        	jqInput.focus();
        }
    },
    
    percentMask: function(input){
        if (!input.readAttribute('masked')) {
        	jqInput = jQuery(input);
        	jqInput.unmaskMoney();
        	jqInput.maskMoney({max: '6'});
        	jqInput.addClass('right');  
        	jqInput.writeAttribute('masked',true);
        	jqInput.focus();
        }
    },

	percentMask4: function(input){
        if (!input.readAttribute('masked')) {
        	jqInput = jQuery(input);
        	jqInput.unmaskMoney();
        	jqInput.maskMoney({max: '8', precision: 4});
        	jqInput.addClass('right');  
        	jqInput.writeAttribute('masked',true);
        	jqInput.focus();
        }
    },
    
    skipOnMaxTo: function(input,nextId){
        Event.observe(input, 'keyup', function (event) {
            saltaCampo(input,nextId);
        });
    },
    
    disable: function(input,state) {
    	jqInput = jQuery(input);
    	if (state) {
    		jqInput.attr('disabled', 'disabled');
    		jqInput.addClass("leitura");
    	}
    	else {
        	$(jqInput).attr('disabled', '');
        	jqInput.removeClass("leitura");
    	}
    },

    skipOnEnterTo: function(input,nextId){
        Event.observe(input, 'keypress', function (event) {
            saltarNoEnter(event,nextId);
        });
    }

};

Element.addMethods('INPUT', UtilsMethods);

function mascara_precisao_decimal(o,i,d){
    v_obj=o;
    v_int=i;
    v_dec=d;
	v_ant=o.value;
    v_fun=mascara_precisao_decimal1;
    setTimeout("exec_mascara_precisao_decimal1()",1);
}

function exec_mascara_precisao_decimal1(){
    v_obj.value=mascara_precisao_decimal1(v_obj.value,v_ant,v_int,v_dec);
}

function mascara_precisao_decimal1(v, v_ant, inteiro, decimal) {

	var qtInteiro = inteiro + inteiro / 3;
	
	if (inteiro > 3) {
		qtInteiro = inteiro + inteiro / 3;
	} else {
		qtInteiro = inteiro;
	}
	
	var virgula = v.indexOf(',');
	var numero_inteiro;
	var numero_decimal;

	if (virgula < 0) {
		numero_inteiro = v;
		numero_decimal = "";
	} else {
		numero_inteiro = v.substring(-1, virgula);
		numero_decimal = v.substring(virgula + 1, v.length);
	}

	if (numero_inteiro.length > qtInteiro || numero_decimal.length > decimal) {
		return v_ant;
	}
	
	if (v.indexOf(',') < 0) {
		return mascara_inteiro(v, inteiro);
	} else {
		return mascara_inteiro(numero_inteiro, inteiro) + ','+ mascara_decimal(numero_decimal, decimal);
	}
}

function mascara_inteiro(v, inteiro) {
	if (v.length <= (inteiro + (inteiro / 3))) {
		v = v.replace(/\D/g, "");

		var saida = v.substring(v.length - 3, v.length);

		var cont = 1;
		while (3 * (cont) < v.length) {
			saida = v.substring(v.length - ((3 * (cont + 1))), v.length
					- (3 * cont))
					+ '.' + saida;
			cont++;
		}
		return saida;
	} else {
		return v.substring(0, v.length - 1);
	}
}

function mascara_decimal(v, decimal) {
	v = v.replace(/\D/g, "");
	if (v.length > decimal) {
		return v.substring(-1, (decimal));

	} else {
		return v;
	}
}

