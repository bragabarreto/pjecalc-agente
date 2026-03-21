//-------------------------------------------------------------------------------//
// JavaScript Document   
//-------------------------------------------------------------------------------// 
//
// Arquivo      : geral.js
// Descricao    : Funcoes Auxiliares (de Apoio ao Componentes Jsf) 
// Uso          : Geral
// Autor		: Ernani Jacob (ernani.jacob@cobra.com.br)xxxx
//
//-------------------------------------------------------------------------------//

//-------------------------------------------------------------------------------------
// Funcao trim para retirar espacos em branco no inicio e no final de um objeto string.
//-------------------------------------------------------------------------------------

String.prototype.trim = function() { 
	return this.replace(/^\s+|\s+$/, ''); 
};

//-----------------------------------------------
// Funcao que Alerta para sair do sistema
//-----------------------------------------------
function ConfirmaSaida(){
	question = confirm("Deseja sair da aplica��o?")
	if (question !="0"){
	//	window.open('','_parent','');
		//window.close();
		return true;
	}else{
		return false;
	}
}


//-----------------------------------------------
// Funcao que Retorna Data Atual do Cliente
//-----------------------------------------------
function DataAtual(){
		var data= new Date()
		document.write("<span title='"+data.toLocaleString()+"'>"+formatDate(data, "dd/MM/yyyy")+"</span>");
}
function addZero(vNumber){ 
    return ((vNumber < 10) ? "0" : "") + vNumber 
} 
function formatDate(vDate, vFormat){ 
    var vDay                      = addZero(vDate.getDate()); 
    var vMonth            = addZero(vDate.getMonth()+1); 
    var vYearLong         = addZero(vDate.getFullYear()); 
    var vYearShort        = addZero(vDate.getFullYear().toString().substring(3,4)); 
    var vYear             = (vFormat.indexOf("yyyy")>-1?vYearLong:vYearShort) 
    var vHour             = addZero(vDate.getHours()); 
    var vMinute           = addZero(vDate.getMinutes()); 
    var vSecond           = addZero(vDate.getSeconds()); 
    var vDateString       = vFormat.replace(/dd/g, vDay).replace(/MM/g, vMonth).replace(/y{1,4}/g, vYear) 
    vDateString           = vDateString.replace(/hh/g, vHour).replace(/mm/g, vMinute).replace(/ss/g, vSecond) 
    return vDateString 
  } 
  
//-------------------------------------------------------------------------------//
// Fun��o para exibir ou ocultar um objeto(div).
//-------------------------------------------------------------------------------//
function aparece(OPCAO){
	if( document.getElementById(OPCAO).style.display == 'none' ){
		document.getElementById(OPCAO).style.display = 'block';
	}
	else {
		document.getElementById(OPCAO).style.display = 'none'
	} 
}
 
/* --------------------------------
   Fun��o para exibir o aguarde.
   -------------------------------- */
function AguardeShow(){
	//jQuery("#DIVaguarde").animate({height: 'toggle', opacity: 'show'}, 'fast');
	Richfaces.showModalPanel('formulario:msgAguarde');
}

/* --------------------------------
   Fun��o para ocultar o aguarde.
   -------------------------------- */
function AguardeHide(){
	//jQuery('#DIVaguarde').animate({height: 'toggle', opacity: 'hide'}, 'fast');
	Richfaces.hideModalPanel('formulario:msgAguarde');
}

/* --------------------------------
Fun��o para exibir o aguarde na tela de login.
-------------------------------- */
function AguardeLoginShow(){
	Richfaces.showModalPanel('login:msgAguarde');
}

/* --------------------------------
Fun��o para ocultar o aguarde na tela de login.
-------------------------------- */
function AguardeLoginHide(){
	Richfaces.hideModalPanel('login:msgAguarde');
}

/* --------------------------------
Fun��o para parar uma requisi��o
-------------------------------- */
function stopRequest() {

	if(navigator.appName == "Microsoft Internet Explorer"){
		window.document.execCommand('Stop');
	} else {
		window.stop();
	}	
			
}

/* --------------------------------
Fun��o para esconder aguarde com a tecla ESC

Chamada: <body onkeyup="tecla(event)">
-------------------------------- */
function tecla(evt) {
    var charCode = evt.keyCode ? evt.keyCode : evt.which ? evt.which : evt.charCode;
    if (charCode==27) { //TECLA ESC
   		AguardeHide();
        if (window.navigator.appName.indexOf("Netscape")!=0) { //SOMENTE PARA O IE
            event.keyCode = 0;
            event.returnValue = false;
        }
    }
}

//-------------------------------------------------------------------------------//
// Fun��o gen�rica para abrir o popup.
//-------------------------------------------------------------------------------//
function lovChamada(arg0){
	var str = null;
	var lovParam = 'lovCall=true';
	if (arg0.indexOf('?')==-1)
		str = arg0 + '?' + lovParam;
	else
	    str = arg0 + '&' + lovParam;

	var altura = 420;
	var largura = 701;
 //   var x = parseInt((screen.width-largura)/2);
 //   var y = parseInt((screen.height-altura)/2);
    
	// Alteracoes para abrir a Janela sempre no centro da tela
    w = screen.width;
    h = screen.height;
    meio_w = w/2;
    meio_h = h/2;
    altura2 = altura/2;
    largura2 = largura/2;
    meio1 = meio_h-altura2;
    meio2 = meio_w-largura2;
    
    var win = window.open(str, 'lov','scrollbars=yes,toolbar=no,location=no,directories=no,status=no, menubar=no,resizable=no,height=' + altura + ',width=' + largura + ',top='+meio1+',left='+meio2+''); 
    
    // var win = window.showModalDialog(str, window, "dialogWidth: " + largura + "px; dialogHeight: " + altura + "px; dialogTop: " + x + "; dialogLeft: " + y + "; resizable: 0");

   // var win = window.open(str, 'lov', 'width='+largura+', height='+altura+', top=' + x + ', left=' + y + ', resizable=no, toolbar=no, location=no, status=no, menubar=no, scrollbars=yes, directories=no');
}

//-------------------------------------------------------------------------------//
//Fun��o gen�rica para abrir o popup como um modal.
//-------------------------------------------------------------------------------//
function lovChamadaModal(arg0){
	var str = null;
	var lovParam = 'lovCall=true';
	if (arg0.indexOf('?')==-1)
		str = arg0 + '?' + lovParam;
	else
	    str = arg0 + '&' + lovParam;

	var altura = 420;
	var largura = 701;
    var x = parseInt((screen.width-largura)/2);
    var y = parseInt((screen.height-altura)/2);
    
    altura = 385;
    largura = 780;
    
    var win = window.showModalDialog(str, window, "dialogWidth: " + largura + "px; dialogHeight: " + altura + "px; dialogTop: " + x + "; dialogLeft: " + y + "; resizable: 0");

}

//-------------------------------------------------------------------------------//
// Fun��o para fechar o pop-up do LOV.
//-------------------------------------------------------------------------------//

function fecharLov() {
	win.close();
}  

//-------------------------------------------------------------------------------//
// Fun��o gen�rica para abrir um popup do tamanho da tela do sistema.
//-------------------------------------------------------------------------------//
function janelaChamada(arg0){
	var str = null;
	var janelaParam = 'lovCall=true';
	if (arg0.indexOf('?')==-1)
		str = arg0 + '?' + janelaParam;
	else
	    str = arg0 + '&' + janelaParam;

	var altura = 700;
	var largura = 1010;
    var x = parseInt((screen.width-largura)/2);
    var y = parseInt((screen.height-altura)/2);
    var win = window.open(str,'','width='+largura+',height='+altura+'top=0,left=0,toolbar=no,location=no,directories=no,status=no,menubar=no,scrollbars=yes,resizable=no,copyhistory=no');
    win.moveTo(x,y);
  	//window.open(str,'popup','width=701,height=420,top=0,left=0,toolbar=no,location=no,directories=no,status=no,menubar=no,scrollbars=auto,resizable=no,copyhistory=no');
}  
  
//-------------------------------------------------------------------------------//
// 
//-------------------------------------------------------------------------------//
//
// Descri??o    : (Mascara para campos inputText)
// Uso          : Geral (Mascara para campos inputText)
// Autor		: Marcus Paulo (marcuspaulo.melo@cobra.com.br)
//
//-------------------------------------------------------------------------------//
//-------------------------------------------------------------------------------//
// para utilizar a mascara basta passar como parametro o nome do campo e o 
// tipo atraves de uma fun��o do Java Script
//    	Falta IMPLEMENTAR CPF, CNPJ, TELEFONE, CEP, NOME
//-------------------------------------------------------------------------------//
//
//-----------------------ATEN��O!! M�SCARA NUM�RICA!!----------------------------//
//
// Foi DESATIVADA, na M�SCARA NUM�RICA (arquivo: mascara/jquery.alphanumeric.pack.js),
// a TRAVA DE CTRL + V e a TRAVA DE BOT�O DIREITO,
// deixando assim o usu�rio "Colar" nos campos!
//
// POR�M, isto deixa a m�scara fraca, pois permite que sejam "colados"
// caracteres n�o-num�ricos no campo.
//
// Uma vez que � importante deixar a op��o de Colar para o usu�rio, especialmente
// n�meros (CNPJ, por exemplo, � trabalhoso de digitar, sendo mais f�cil Colar),
// recomenda-se que, apesar da utiliza��o desta m�scara, tamb�m seja feita uma
// VALIDA��O NO LADO DO SERVIDOR, para n�o deixar passar caracteres n�o-num�ricos, que
// a m�scara pode deixar passar com a utiliza��o do Colar.
function mascara(campo, tipo){
	mascaraFormulario('formulario', campo, tipo);

}

function mascaraFormulario(formulario, campo, tipo){

	var $j = jQuery.noConflict();
	
	$j(function() {
	
		switch(tipo){
		
		case 'AUTOCOMPLETE':
   			var nome = formulario + ':' + campo;
			if ($(nome) != null && !$(nome).disabled) {
				var auto = $j('textarea[name=' + nome + ']');
				expandirAutocomplete(auto);				
			}
   			break;
		case 'DATA':
			$j('input[name=' + formulario + ':' + campo + 'InputDate]').mask('99/99/9999');
   			break;
   		case 'MESANO':
   			$j('input[name=' + formulario + ':' + campo + ']').mask('99/9999');
   			break;
 		case 'ANOMES':
 			$j('input[name=' + formulario + ':' + campo + ']').mask('9999/99');
 			break;
 		case 'ANOSAFRA':
 			$j('input[name=' + formulario + ':' + campo + ']').mask('9999/9999');
 			break;
   		case 'INTEIRO':
   			$j('input[name=' + formulario + ':' + campo + ']').numeric({allow:""});
   			break;
   		case 'DIVISOR':
   		$j('input[name=' + formulario + ':' + campo + ']').masktextcomma();
   			
   			var nome = formulario + ':' + campo;
   			
   			$j('input[name=' + nome + ']').keyup(function(event){
   			
   				var nomeTemp = $j(this).val();
   	   			
   	   			var substr = nomeTemp.split(",");
   	   			
   	   			if(event.keyCode!=37 && event.keyCode!=39 && substr[1].length>4){
   	   				var newStr = nomeTemp.substring(0, nomeTemp.length-1);
   	   				$j(this).val(newStr);
   	   			}
   	   	
   	   		});
   			break;
   		case 'MULTIPLICADOR':
   	   		$j('input[name=' + formulario + ':' + campo + ']').masktextcomma();
   	   			
   	   			var nome = formulario + ':' + campo;
   	   			
   	   			$j('input[name=' + nome + ']').keyup(function(event){
   	   			
   	   				var nomeTemp = $j(this).val();
   	   	   			
   	   	   			var substr = nomeTemp.split(",");
   	   	   			
   	   	   			if(event.keyCode!=37 && event.keyCode!=39 && substr[1].length>6){
   	   	   				var newStr = nomeTemp.substring(0, nomeTemp.length-1);
   	   	   				$j(this).val(newStr);
   	   	   			}
   	   	   	
   	   	   		});
   	   			break;
   		case 'HORA':
   			$j('input[name=' + formulario + ':' + campo + ']').mask('99:99');
   			break;
   		case 'DATAHORA':
   			$j('input[name=' + formulario + ':' + campo + 'InputDate]').mask('99/99/9999 99:99');
   			break;
   		case 'MOEDA':
   			//$j('input[name=' + formulario + ':' + campo + ']').maskFinancial();
   			$j('input[name=' + formulario + ':' + campo + ']').unmaskMoney();
   			$j('input[name=' + formulario + ':' + campo + ']').maskMoney();
   			$j('input[name=' + formulario + ':' + campo + ']').addClass('right');  
   			break;
   		case 'AREA4':
   			$j('input[name=' + formulario + ':' + campo + ']').unmaskMoney();
   			$j('input[name=' + formulario + ':' + campo + ']').maskMoney({precision: 4});
   			$j('input[name=' + formulario + ':' + campo + ']').addClass('right');
   			break;
   		case 'MOEDAMENOS':
   			//$j('input[name=' + formulario + ':' + campo + ']').maskFinancial({menos:true});
   			$j('input[name=' + formulario + ':' + campo + ']').unmaskMoney();
   			$j('input[name=' + formulario + ':' + campo + ']').maskMoney({allowNegative: true});
   			$j('input[name=' + formulario + ':' + campo + ']').addClass('right');
   			break;
   		case 'PORCENTAGEM':
   			//$j('input[name=' + formulario + ':' + campo + ']').maskFinancial({max:'6'}); 
   			$j('input[name=' + formulario + ':' + campo + ']').unmaskMoney();
   			$j('input[name=' + formulario + ':' + campo + ']').maskMoney({max: '6'});
   			$j('input[name=' + formulario + ':' + campo + ']').addClass('right');
   		
   			break;
   		case 'TELEFONE':
   			$j('input[name=' + formulario + ':' + campo + ']').mask('9999-9999');
   			break;
   		case 'DDD':
   			$j('input[name=' + formulario + ':' + campo + ']').mask('(99)');
   			break;
   		case 'TEXTO':
   			$j('input[name=' + formulario + ':' + campo + '], textarea[name=' + formulario + ':' + campo + ']').masktext({allow:""});
   			break;
   		case 'TEXTOAREA':
   			$j('textarea[name=' + formulario + ':' + campo + ']').masktext({allow:"\n"});
   			break;
   		case 'TEXTOAREANUMERO':
   			$j('textarea[name=' + formulario + ':' + campo + ']').masktextnumeric({allow:"\n"});
   			break;    			   			
   		case 'TEXTONUMERO':
   			$j('input[name=' + formulario + ':' + campo + ']').masktextnumeric({allow:""});
   			break;   	
		case 'COORDENADA':
   			$j('input[name=' + formulario + ':' + campo + ']').mask('99�99'+"'"+'99"a');
   			break;
   		case 'CPF':
   			$j('input[name=' + formulario + ':' + campo + ']').mask('999.999.999-99');
   			break;
   		case 'CNPJ':
   			$j('input[name=' + formulario + ':' + campo + ']').mask('99.999.999/9999-99');   			
   			break;
   		case 'CEP':
   			$j('input[name=' + formulario + ':' + campo + ']').mask('99999-999'); 
   			break;
   		case 'EMAIL':
   			$j('input[name=' + formulario + ':' + campo + ']').alphanumeric({allow:"._-@"});
   			break;
   		case 'SITE':
   			$j('input[name=' + formulario + ':' + campo + ']').alphanumeric({allow:"/:.-?&;~+=%#@"});
   			break;
   		case 'MOEDA142':
   			//$j('input[name=' + formulario + ':' + campo + ']').maskFinancial({max:'14'});
   			$j('input[name=' + formulario + ':' + campo + ']').unmaskMoney();
   			$j('input[name=' + formulario + ':' + campo + ']').maskMoney({max: '14'});
   			break;
   		case 'MOEDA202':
   			//$j('input[name=' + formulario + ':' + campo + ']').maskFinancial({max:'20'});
   			$j('input[name=' + formulario + ':' + campo + ']').unmaskMoney();
   			$j('input[name=' + formulario + ':' + campo + ']').maskMoney({max: '20'});
   			break;
   		case 'LOV':
   			var nome = formulario + ':' + campo;
			if ($(nome) != null && !$(nome).disabled) {
				
				var lov = $j('input[name=' + nome + ']');
				
				if (lov.attr('type') == undefined) {
					lov = $j('textarea[name=' + nome + ']');
					expandirLov(lov);
				}
				
				if (lov.val() == '') {
					lov.val('CLIQUE NA LUPA');
				} 
				setReadonly(campo);
			}
   			break;
     					
		}
	});
 }
 	
function focusCampo(campo) {
    
    if ( campo != null ){
        document.forms[0].getElementById('formulario:'+campo).focus();
    } else {
     try{
        var oField;
        if (document.forms.length > 0) {
            for (var i=0; i < document.forms[0].elements.length; ++i) {
                oField = document.forms[0].elements[i];
                if ((oField.type == "text") || (oField.type == "textarea")) {
                    if (oField.disabled!=true) {
                        	oField.focus();
                        break;
                    }
                }
            }
        }
     }catch(err){}	
    }          
}

 function limparComMascara(campo, tipo) {
	 if ( (tipo == 'DATAHORA') || (tipo == 'DATA') ){
		 jQuery('input[name=formulario:'+campo+'InputDate]').unmask();
		 input = document.getElementById('formulario:'+campo+'InputDate');
		 //input = jQuery('input[name=formulario:'+campo+'InputDate]');
	 } else {
		 jQuery('input[name=formulario:'+campo+']').unmask();
		 input = document.getElementById('formulario:'+campo);
		 //input = jQuery('input[name=formulario:'+campo+']');
	 }		 
	 input.value = '';
	 mascara(campo, tipo);
	 //input.focus();
 }

// Limitar tamanho TextArea
function limitarTextArea(campo, total){
    tam = campo.value.length;
    str="";
    str=str+tam;
    //document.getElementById("digitado").innerHTML = str;
    //document.getElementById("restante").innerHTML = total - str;
    if (tam > total){
        aux = campo.value;
        campo.value = aux.substring(0,total);
        //document.getElementById("digitado").innerHTML = total;
        //document.getElementById("restante").innerHTML = 0;
      }
}

function limpaCombo(combo) {
	// verifica se o combo possui a op��o padr�o "..."
	if (combo.options[0] != null && combo.options[0].text == '...') {
		combo.selectedIndex = 0;							
        try {
			combo.onchange();
		} catch(err) {
			// faz nada, apenas passa silenciosamente...
		}
	} else {
		combo.selectedIndex = -1;
	}
}

//-------------------------------------------------------------------------------//
// Fun��o gen�rica para limpar os campos de um formul�rio.
// Para utiliz�-la, deve-se passar como par�metro um Array contendo os campos
// a serem limpados.
// Exemplo: limpa(new Array('codigo','descricao'))
// Colocar no atributo onclick do bot�o.
//-------------------------------------------------------------------------------//
 function limpa(camposArray) {
	for(i = 0 ; i < camposArray.length; i++) {
		  var campo = document.getElementById('formulario:'+camposArray[i]);
	  if (campo != null) {
          if ((campo.type == "text") || (campo.type == "textarea") || (campo.type == "hidden")) {
			campo.value = "";
          } else if (campo.type == "checkbox") {
			campo.checked = false;
	      } else if(campo.type == "select-one"){
			limpaCombo(campo);
          } else if(campo.type == "radio"){
			campo.checked = false;
          }
	  }
	  
	}
 }
 
//-------------------------------------------------------------------------------//
// Fun��o gen�rica para limpar todos os campos de um formul�rio.
// Colocar no atributo onclick do bot�o.
//-------------------------------------------------------------------------------//
 function limpaTudo() {

        var oField;
        if (document.forms.length > 0) {
            for (var i=0; i < document.forms[0].elements.length; ++i) {
                oField = document.forms[0].elements[i];
                if(!possuiClassName(oField, 'leitura')){
	                if ((oField.type == "text") || (oField.type == "textarea")) {
	                    if (oField.disabled!=true) {
							oField.value="";
	                    }
	                } else if (oField.type == "checkbox") {
	                    if (oField.disabled!=true) {
							oField.checked=false;
	                    }
	                } else if(oField.type == "select-one"){
	                	if (oField.disabled!=true) {
							oField.selectedIndex = 0;
	                    }
	                } else if(oField.type == "radio"){
	                	if (oField.disabled!=true) {
							oField.checked = false;
	                    }
	                }
                }
            }
        }
        focusCampo();
}
   
// Validar data no formato dd/mm/aaaa
function validarData(data){
	var er = /^((0[1-9]|[12]\d)\/(0[1-9]|1[0-2])|30\/(0[13-9]|1[0-2])|31\/(0[13578]|1[02]))\/\d{4}$/;
	return er.test(data);
}   

//-------------------------------------------------------------------------------//
// Fun��o para retirar caracateres especiais e espacos em branco.
//-------------------------------------------------------------------------------//
function ajustaTexto(campo) {
	var Acentos =  "������������������������������������������������_�'@#$!%^&*(){}+=~`�����������|\"\\-.,;:?[]/<>0123456789";
	var Traducao = "AEIOUAEIOUAEOAEIOUAONaeiouaeiouaeiouaeiouaonCCyY*****************************************************";

   var Posic, Carac;
   var TempLog = "";

   for (var i=0; i < campo.value.length; i++) {
	   Carac = campo.value.toUpperCase().charAt (i); // a
	   Posic = Acentos.indexOf (Carac); // 1
	   if (Posic > -1){
	      	TempLog += Traducao.charAt (Posic);
	   } else
	      TempLog += campo.value.toUpperCase().charAt (i);
   }
   campo.value = TempLog.replace( new RegExp(/\*/g), "") ;
   campo.value = campo.value.trim();
}

//-------------------------------------------------------------------------------//
// Fun��o para retirar caracateres especiais apenas, permitindo letras e numeros.
//-------------------------------------------------------------------------------//
function ajustaTextoComNumero(campo) {
	var Acentos =  "������������������������������������������������_�'@#$!%^&*(){}+=~`�����������|\"\\-.,;:?[]/<>";
	var Traducao = "AEIOUAEIOUAEOAEIOUAONaeiouaeiouaeiouaeiouaonCCyY*******************************************";

    var Posic, Carac;
    var TempLog = "";

    for (var i=0; i < campo.value.length; i++) {
	   Carac = campo.value.toUpperCase().charAt (i); // a
	   Posic = Acentos.indexOf (Carac); // 1
	   if (Posic > -1){
	      	TempLog += Traducao.charAt (Posic);
	   } else
	      TempLog += campo.value.toUpperCase().charAt (i);
    }
    campo.value = TempLog.replace( new RegExp(/\*/g), "") ;
    campo.value = campo.value.trim();
}


//-------------------------------------------------------------------------------//
// Fun��o para retirar caracateres especiais e letras, permitindo apenas numeros com ponto
//-------------------------------------------------------------------------------//
function ajustaTextoNumeroComPonto(campo) {
	var Acentos =  "ABCDEFGHIJLMNOPQRSTUVXZWYK������������������������������������������������_�'@#$!%^&*(){}+=~`�����������|\"\\-.,;:?[]/<>";
	var Traducao = "************************************************************************************************************.*********";

    var Posic, Carac;
    var TempLog = "";

    for (var i=0; i < campo.value.length; i++) {
	   Carac = campo.value.toUpperCase().charAt (i); // a
	   Posic = Acentos.indexOf (Carac); // 1
	   if (Posic > -1){
	      	TempLog += Traducao.charAt (Posic);
	   } else
	      TempLog += campo.value.toUpperCase().charAt (i);
    }
    campo.value = TempLog.replace( new RegExp(/\*/g), "") ;
    campo.value = campo.value.trim();
}

//-------------------------------------------------------------------------------//
// Fun��o para retirar caracateres especiais e letras, permitindo apenas numeros.
//-------------------------------------------------------------------------------//
function ajustaTextoApenasNumero(campo) {
	var Acentos =  "ABCDEFGHIJLMNOPQRSTUVXZWYK������������������������������������������������_�'@#$!%^&*(){}+=~`�����������|\"\\-.,;:?[]/<>";
	var Traducao = "*********************************************************************************************************************";

    var Posic, Carac;
    var TempLog = "";

    for (var i=0; i < campo.value.length; i++) {
	   Carac = campo.value.toUpperCase().charAt (i); // a
	   Posic = Acentos.indexOf (Carac); // 1
	   if (Posic > -1){
	      	TempLog += Traducao.charAt (Posic);
	   } else
	      TempLog += campo.value.toUpperCase().charAt (i);
    }
    campo.value = TempLog.replace( new RegExp(/\*/g), "") ;
    campo.value = campo.value.trim();
}


//-------------------------------------------------------------------------------//
// Fun��o para retirar caracateres especiais e letras, permitindo apenas numeros, ponto e virgula.
//-------------------------------------------------------------------------------//
function ajustaTextoApenasNumeroPontoEVirgula(campo) {
	var Acentos =  "ABCDEFGHIJLMNOPQRSTUVXZWYK������������������������������������������������_�'@#$!%^&*(){}+=~`�����������|\"\\-.,;:?[]/<>";
	var Traducao = "************************************************************************************************************.,********";

    var Posic, Carac;
    var TempLog = "";
	
	for (var i=0; i < campo.value.length; i++) {
	   Carac = campo.value.toUpperCase().charAt (i); // a
	   Posic = Acentos.indexOf (Carac); // 1
	   if (Posic > -1){
	      	TempLog += Traducao.charAt (Posic);
	   } else
	      TempLog += campo.value.toUpperCase().charAt (i);
	}
    campo.value = TempLog.replace( new RegExp(/\*/g), "") ;
    campo.value = campo.value.trim();
}


//-------------------------------------------------------------------------------//
// Fun��o para retirar caracateres especiais e letras, permitindo apenas numeros e / e - .
//-------------------------------------------------------------------------------//
function ajustaTextoComNumeroBarraHifen(campo) {
	var Acentos =  "ABCDEFGHIJLMNOPQRSTUVXZWYK������������������������������������������������_�'@#$!%^&*(){}+=~`�����������|\"\\-.,;:?[]/<>";
	var Traducao = "ABCDEFGHIJLMNOPQRSTUVXZWYK*********************************************************************************-*******/**";

    var Posic, Carac;
    var TempLog = "";
	
	for (var i=0; i < campo.value.length; i++) {
	   Carac = campo.value.toUpperCase().charAt (i); // a
	   Posic = Acentos.indexOf (Carac); // 1
	   if (Posic > -1){
	      	TempLog += Traducao.charAt (Posic);
	   } else
	      TempLog += campo.value.toUpperCase().charAt (i);
	}
    campo.value = TempLog.replace( new RegExp(/\*/g), "") ;
    campo.value = campo.value.trim();
}


//-------------------------------------------------------------------------------//
//Fun��o para converter texto para letras mai�sculas
//-------------------------------------------------------------------------------//
function ajustaTextoParaUpperCase(campo) {
	campo.value = campo.value.toUpperCase()
}



//-----------------------------------------------------------------------------------
// Fun��o para retirar caracateres especiais e espacos em branco em toda submiss�o.
//-----------------------------------------------------------------------------------
function ajustaTextoSubmit() {

        var oField;
        if (document.forms.length > 0) {
            for (var i=0; i < document.forms[0].elements.length; ++i) {
                oField = document.forms[0].elements[i];
                if ((oField.type == "text") || (oField.type == "textarea")) {
                    if ( oField.disabled!=true && !possuiClassName(oField, "ajusteIgnorado") && !possuiClassName(oField, "rich-calendar-input") ) {
						ajustaTexto(oField);
                    }
                }
            }
        }
        focusCampo();
}

function possuiClassName(objElement, strClass){
   if ( objElement.className ){
   	  return objElement.className.indexOf(strClass) != -1;// se igual a -1, n�o possui a className
   }
}

//------------------------------------------------------------------------------------------------------------
// Fun��o para n�o permitir entrada texto.
// Exemplo: <h:inputText onkeydown="return campoLeitura(event);" onkeypress="return campoLeitura(event);" />
// Colocar no atributo onkeypress e onkeypress do bot�o.
//------------------------------------------------------------------------------------------------------------
function campoLeitura(e) {

	var keychar;
	if(window.event){ // IE
	  keychar = e.keyCode;
	} else if(e.which || e.which==0){ // Netscape/Firefox/Opera
	  	keychar = e.which;
      }
	if (keychar == 0 || keychar == 9 || keychar == 13 ){
		return true;
	}else {
		return false;
	}
}

//---------------------------------------------------------------------------------------
// Fun��es para formata��o e tratamente de moedas usando javascript
//---------------------------------------------------------------------------------------
function moeda2float(moeda){
   moeda = moeda.replace(/\./g, "").replace(/,/g, ".");
   return parseFloat(moeda);
}

function float2moeda(num) {
   x = 0;
   if(num<0) {
      num = Math.abs(num);
      x = 1;
   }
   if(isNaN(num)) num = "0";
      cents = Math.floor((num*100+0.5)%100);

   num = Math.floor((num*100+0.5)/100).toString();

   if(cents < 10) 
   		cents = "0" + cents;

   for (var i = 0; i < Math.floor((num.length-(1+i))/3); i++){
         num = num.substring(0,num.length-(4*i+3)) + '.' + num.substring(num.length-(4*i+3));
   }

   ret = num + ',' + cents;

   if (x == 1) 
   		ret = ' - ' + ret;
   		
   	return ret;
}

//------------------------------------------------------------------
// Fun��o para formatar campos financeiros.
// Colocar no atributo onkeypress do bot�o.
// Exemplo: <h:inputText onkeydown="financeiro(this,11,event,2)" />
//------------------------------------------------------------------
function financeiro(campo,tammax,teclapres,decimal) {

	//campo.oncontextmenu = new Function("return false;");
	
	var tecla;
	if (teclapres.srcElement){  
		tecla = teclapres.keyCode;
	} else {
		if (teclapres.target){
			tecla = teclapres.which;
		}
	}		

	if (tecla == 9 || tecla == 13 || tecla == 0 || teclapres.ctrlKey && tecla == 67 || teclapres.ctrlKey && tecla == 86 ) return true; // 
	if ( ( tecla != 8 ) && !( tecla >= 48 && tecla <= 57 ) && !( tecla >= 96 && tecla <= 105 ) ) return false; // 48:0 - 57:9; 6:<-
	
	var valor_limpo = "";
	var contador;
	for (var i=0; i < campo.value.length; i++) {
		contador = "0123456789".indexOf(campo.value.substring(i, i+1));
		if (contador >= 0) {
			valor_limpo += contador;
		}
	}
	vr = valor_limpo;
	tam = vr.length;
	dec = decimal;
	
	if ( tam < tammax && tecla != 8 ){ 
		tam = vr.length + 1 ; 
	}
	if ( tecla == 8 ) { 
		tam = tam - 1 ; 
	}
	if ( tam <= dec ){
		campo.value = vr ; 
	}
	if ( (tam > dec) && (tam <= 5) ){
		campo.value = vr.substr( 0, tam - 2 ) + "," + vr.substr( tam - dec, tam ) ; 
	}
	if ( (tam >= 6) && (tam <= 8) ){
		campo.value = vr.substr( 0, tam - 5 ) + "." + vr.substr( tam - 5, 3 ) + "," + vr.substr( tam - dec, tam ) ; 
	}
	if ( (tam >= 9) && (tam <= 11) ){
		campo.value = vr.substr( 0, tam - 8 ) + "." + vr.substr( tam - 8, 3 ) + "." + vr.substr( tam - 5, 3 ) + "," + vr.substr( tam - dec, tam ) ; 
	}
	if ( (tam >= 12) && (tam <= 14) ){
		campo.value = vr.substr( 0, tam - 11 ) + "." + vr.substr( tam - 11, 3 ) + "." + vr.substr( tam - 8, 3 ) + "." + vr.substr( tam - 5, 3 ) + "," + vr.substr( tam - dec, tam ) ; 
	}
	if ( (tam >= 15) && (tam <= 17) ){
		campo.value = vr.substr( 0, tam - 14 ) + "." + vr.substr( tam - 14, 3 ) + "." + vr.substr( tam - 11, 3 ) + "." + vr.substr( tam - 8, 3 ) + "." + vr.substr( tam - 5, 3 ) + "," + vr.substr( tam - 2, tam ) ;
	}
	return true;
}
function ajustaFinanceiro(campo,decimal) {
	var valor_limpo = "";
	var contador;
	for (var i=0; i < campo.value.length; i++) {
		contador = "0123456789".indexOf(campo.value.substring(i, i+1));
		if (contador >= 0) {
			valor_limpo += contador;
		}
	}
	vr = valor_limpo;
	tam = vr.length;
	dec = decimal;
	
	if ( tam <= dec ){
		campo.value = vr ; 
	}
	if ( (tam > dec) && (tam <= 5) ){
		campo.value = vr.substr( 0, tam - 2 ) + "," + vr.substr( tam - dec, tam ) ; 
	}
	if ( (tam >= 6) && (tam <= 8) ){
		campo.value = vr.substr( 0, tam - 5 ) + "." + vr.substr( tam - 5, 3 ) + "," + vr.substr( tam - dec, tam ) ; 
	}
	if ( (tam >= 9) && (tam <= 11) ){
		campo.value = vr.substr( 0, tam - 8 ) + "." + vr.substr( tam - 8, 3 ) + "." + vr.substr( tam - 5, 3 ) + "," + vr.substr( tam - dec, tam ) ; 
	}
	if ( (tam >= 12) && (tam <= 14) ){
		campo.value = vr.substr( 0, tam - 11 ) + "." + vr.substr( tam - 11, 3 ) + "." + vr.substr( tam - 8, 3 ) + "." + vr.substr( tam - 5, 3 ) + "," + vr.substr( tam - dec, tam ) ; 
	}
	if ( (tam >= 15) && (tam <= 17) ){
		campo.value = vr.substr( 0, tam - 14 ) + "." + vr.substr( tam - 14, 3 ) + "." + vr.substr( tam - 11, 3 ) + "." + vr.substr( tam - 8, 3 ) + "." + vr.substr( tam - 5, 3 ) + "," + vr.substr( tam - 2, tam ) ;
	}

}

//-------------------------------------------------------------------
// Fun��o para deixar os campos como somente leitura.
// Colocar no atributo styleClass do campo.
// Exemplo: <h:inputText styleClass="leitura" />
//-------------------------------------------------------------------
function setReadonly(campo) {
    if ( campo != null && $('formulario:'+campo) != null ) {
        $('formulario:'+campo).readOnly = true;
    } else {
		for (i=0; i<document.forms.length; i++) {
	   		for (j=0; j<document.forms[i].elements.length; j++) {
				// "leitura" eh o estilo css utilizados em todos os campos read-only
				var componente = document.forms[i].elements[j];
				
				if ( possuiClassName(componente, 'leitura') ){
			          componente.readOnly = true;
		        }
	        }
	    }
	}
}

//-------------------------------------------------------------------
// Fun��o para ajustar as colunas da tabela, tipo colspan.
// Colocar no atributo styleClass do PanelGroup.
// Exemplo: <h:PanelGroup styleClass="colspan2" />
//-------------------------------------------------------------------
function ajustaTabelas() {
	jQuery("table td span").each( function(index){
		if (this.className.match('^colspan(\\d+)$') != null) {
			this.parentNode.colSpan = this.className.substring(7); 
		}	
	});
}

//-------------------------------------------------------------------
// Fun��o para ajustar as colunas da tabela, tipo colspan.
//-------------------------------------------------------------------
function uppercase(campo) {
	var Acentos =  "����������������������������������������������_�'@#$!%^&*(){}+=~`�����������|\"\\?:<>,.;/[]-";  
	var Traducao = "AEIOUAEIOUAEOAEIOUAOaeiouaeiouaeiouaeiouaoCCyY********************************************";

   var Posic, Carac;
   var TempLog = " ";

   for (var i=0; i < campo.value.length; i++) {
	   Carac = campo.value.toUpperCase().charAt (i); // a
	   Posic = Acentos.indexOf (Carac); // 1
	   if (Posic > -1){
	      	TempLog += Traducao.charAt (Posic);
	   } else
	      TempLog += campo.value.toUpperCase().charAt (i);
   }
   campo.value = TempLog.replace( new RegExp(/\*/g), "") ;
   campo.value = campo.value.trim();
}

function uppercaseSeparador(campo) {
	var Acentos =  "����������������������������������������������_�'@#$!%^&*(){}+=~`�����������|\"\\?:<>,.;/[]";  
	var Traducao = "AEIOUAEIOUAEOAEIOUAOaeiouaeiouaeiouaeiouaoCCyY*******************************************";

   var Posic, Carac;
   var TempLog = " ";

   for (var i=0; i < campo.value.length; i++) {
	   Carac = campo.value.toUpperCase().charAt (i); // a
	   Posic = Acentos.indexOf (Carac); // 1
	   if (Posic > -1){
	      	TempLog += Traducao.charAt (Posic);
	   } else
	      TempLog += campo.value.toUpperCase().charAt (i);
   }
   campo.value = TempLog.replace( new RegExp(/\*/g), "") ;
   campo.value = campo.value.trim();
}

function uppercaseAcentosCedilha(campo) {
	var Acentos =  "�����������������������������������������_�'@#$!%&*(){}+=`����������|\"\\?:<>,.;/[]-";  
	var Traducao = "AEIOU���AEIOU�������aeiou��i�uaeiou����yY*****************************************";

   var Posic, Carac;
   var TempLog = " ";

   for (var i=0; i < campo.value.length; i++) {
	   Carac = campo.value.toUpperCase().charAt (i); // a
	   Posic = Acentos.indexOf (Carac); // 1
	   if (Posic > -1){
	      	TempLog += Traducao.charAt (Posic);
	   } else
	      TempLog += campo.value.toUpperCase().charAt (i);
   }
   campo.value = TempLog.replace( new RegExp(/\*/g), "") ;
   campo.value = campo.value.trim();
}

function uppercaseBarraHifen(campo) {
	var Acentos =  "�����������������������������������������_�'@#$!%&*(){}+=`����������|\"\\?:<>,.;/[]-";  
	var Traducao = "AEIOU���AEIOU�������aeiou��i�uaeiou����yY*************************************/**-";

   var Posic, Carac;
   var TempLog = " ";

   for (var i=0; i < campo.value.length; i++) {
	   Carac = campo.value.toUpperCase().charAt (i); // a
	   Posic = Acentos.indexOf (Carac); // 1
	   if (Posic > -1){
	      	TempLog += Traducao.charAt (Posic);
	   } else
	      TempLog += campo.value.toUpperCase().charAt (i);
   }
   campo.value = TempLog.replace( new RegExp(/\*/g), "") ;
   campo.value = campo.value.trim();
}



//-------------------------------------------------------------------
// Funcao para ocultar e exibir o menu lateral esquerdo (arvore)
//-------------------------------------------------------------------
function HideContent(d) {
	if(d.length < 1) { return; }
	document.getElementById(d).style.display = "none";
}

function ShowContent(d) {
	if(d.length < 1) { return; }
	document.getElementById(d).style.display = "";
}

//-------------------------------------------------------------------
// Funcao para remover a mascara de um campo
//-------------------------------------------------------------------	
 function removerMascara(campo, tipo) {
	 if ( (tipo == 'DATAHORA') || (tipo == 'DATA') ){
		 jQuery('input[name=formulario:'+campo+'InputDate]').unmask();
	 } else {
		 jQuery('input[name=formulario:'+campo+']').unmask();
	 }		 
 }
 
 
 //-------------------------------------------------------------------------------//
// Fun��o para retirar caracateres especiais e espacos em branco.
//-------------------------------------------------------------------------------//
function ajustaTextoAlfaNumerico(campo) {
	var Acentos =  "����������������������������������������������_�'@#$!%^&*(){}+=~`�����������|\"\\-.,;:?[]/<>";
	var Traducao = "AEIOUAEIOUAEOAEIOUAOaeiouaeiouaeiouaeiouao**yY*******************************************";

   var Posic, Carac;
   var TempLog = "";

   for (var i=0; i < campo.value.length; i++) {
	   Carac = campo.value.toUpperCase().charAt (i); // a
	   Posic = Acentos.indexOf (Carac); // 1
	   if (Posic > -1){
	      	TempLog += Traducao.charAt (Posic);
	   } else
	      TempLog += campo.value.toUpperCase().charAt (i);
   }
   campo.value = TempLog.replace( new RegExp(/\*/g), "") ;
   campo.value = campo.value.trim();
}

 //-------------------------------------------------------------------------------//
// Fun��o para retirar caracateres especiais e espacos em branco para cid (permite ponto).
//-------------------------------------------------------------------------------//
function ajustaTextoCID(campo) {
	var Acentos =  "����������������������������������������������_�'@#$!%^&*(){}+=~`�����������|\"\\-.,;:?[]/<>";
	var Traducao = "AEIOUAEIOUAEOAEIOUAOaeiouaeiouaeiouaeiouao**yY**********************************.*********";

   var Posic, Carac;
   var TempLog = "";

   for (var i=0; i < campo.value.length; i++) {
	   Carac = campo.value.toUpperCase().charAt (i); // a
	   Posic = Acentos.indexOf (Carac); // 1
	   if (Posic > -1){
	      	TempLog += Traducao.charAt (Posic);
	   } else
	      TempLog += campo.value.toUpperCase().charAt (i);
   }
   campo.value = TempLog.replace( new RegExp(/\*/g), "") ;
   campo.value = campo.value.trim();
}

//-------------------------------------------------------------------------------//
// Fun��o para remover todos os caracteres que nao sejam numeros em uma string.
//-------------------------------------------------------------------------------//
function ajustaCampoNumerico(campo) {
	campo.value = campo.value.replace(/\D/g,"")
}

//-------------------------------------------------------------------------------//
// Fun��o para remover todos os caracteres que sejam numeros em uma string.
//-------------------------------------------------------------------------------//
function ajustaCampoAlfa(campo) {
	campo.value = campo.value.replace(/\d/g, "");
}

//-------------------------------------------------------------------------------//
// Fun��o para impedir que haja submiss�o de uma p�gina utilizando a tecla enter
// Exemplo: <body onkeypress="return disableEnterKey(event);">
//-------------------------------------------------------------------------------//
function disableEnterKey(e) {
	var key;     
    if(window.event)
    	key = window.event.keyCode; //IE
    else
    	key = e.which; //firefox
   
    return (key != 13);
}

//-------------------------------------------------------------------------------//
// Fun��o para impedir que apare�a o menu de contexto
// Exemplo: <h:inputText onmousedown="document.oncontextmenu = disableContextMenu(event);"
//						 onblur="document.oncontextmenu = new Function('return true;');">
//-------------------------------------------------------------------------------//
function disableContextMenu(e) {
	if (e.button == 2 || e.button == 3) {
		return new Function("return false;");
	}
}

function uppercaseCaracteresEspeciais(campo) {
	var Acentos =  "�����������������������������������������_�'@#$!%&*(){}+=`����������|\"\\?:<>,.;/[]-0123456789";  
	var Traducao = "AEIOU���AEIOU�������aeiou��i�uaeiou����yY*******************************:**,.;/**-**********";

   var Posic, Carac;
   var TempLog = " ";

   for (var i=0; i < campo.value.length; i++) {
	   Carac = campo.value.toUpperCase().charAt (i); // a
	   Posic = Acentos.indexOf (Carac); // 1
	   if (Posic > -1){
	      	TempLog += Traducao.charAt (Posic);
	   } else
	      TempLog += campo.value.toUpperCase().charAt (i);
   }
   campo.value = TempLog.replace( new RegExp(/\*/g), "") ;
   campo.value = campo.value.trim();
}

function uppercasePlacaVeiculo(campo) {
	var Acentos =  "�����������������������������������������_�'@#$!%&*(){}+=`����������|\"\\?:<>,.;/[]-";  
	var Traducao = "AEIOU���AEIOU�������aeiou��i�uaeiou����yY****************************************-";

   var Posic, Carac;
   var TempLog = " ";

   for (var i=0; i < campo.value.length; i++) {
	   Carac = campo.value.toUpperCase().charAt (i); // a
	   Posic = Acentos.indexOf (Carac); // 1
	  
	   if (Posic > -1){
	      	TempLog += Traducao.charAt (Posic);
	   } else
	      TempLog += campo.value.toUpperCase().charAt (i);
   }
   campo.value = TempLog.replace( new RegExp(/\*/g), "") ;
   campo.value = campo.value.trim();
}

 //-------------------------------------------------------------------------------//
// Fun��o para retirar caracateres especiais e espacos em branco.
//-------------------------------------------------------------------------------//
function ajustaTextoPlacaVeiculo(campo) {
	var Acentos =  "�����������������������������������������_�'@#$!%&*(){}+=`����������|\"\\?:<>,.;/[]-";  
	var Traducao = "AEIOU���AEIOU�������aeiou��i�uaeiou����yY****************************************-";

   var Posic, Carac;
   var TempLog = "";

   for (var i=0; i < campo.value.length; i++) {
	   Carac = campo.value.toUpperCase().charAt (i); // a
	   Posic = Acentos.indexOf (Carac); // 1
	   if (Posic > -1){
	      	TempLog += Traducao.charAt (Posic);
	   } else
	      TempLog += campo.value.toUpperCase().charAt (i);
   }
   campo.value = TempLog.replace( new RegExp(/\*/g), "") ;
   campo.value = campo.value.trim();
}

 //-------------------------------------------------------------------------------//
// Fun��o para retirar caracateres especiais e espacos em branco.
//-------------------------------------------------------------------------------//
function ajustaTextoCaracteresEspeciais(campo) {
	var Acentos =  "�����������������������������������������_�'@#$!%&*(){}+=`����������|\"\\?:<>,.;/[]-0123456789";  
	var Traducao = "AEIOU���AEIOU�������aeiou��i�uaeiou����yY*******************************:**,.;/**-**********";

   var Posic, Carac;
   var TempLog = "";

   for (var i=0; i < campo.value.length; i++) {
	   Carac = campo.value.toUpperCase().charAt (i); // a
	   Posic = Acentos.indexOf (Carac); // 1
	   if (Posic > -1){
	      	TempLog += Traducao.charAt (Posic);
	   } else
	      TempLog += campo.value.toUpperCase().charAt (i);
   }
   campo.value = TempLog.replace( new RegExp(/\*/g), "") ;
   campo.value = campo.value.trim();
}

 //-------------------------------------------------------------------------------//
// Fun��o para retirar caracateres especiais (deixando o espaco).
//-------------------------------------------------------------------------------//
function ajustaTextoCaracteresEspeciaisEspaco(campo) {
	var Acentos =  "�����������������������������������������_�'@#$!%&*(){}+=`����������|\"\\?:<>,.;/[]-0123456789";  
	var Traducao = "AEIOU���AEIOU�������aeiou��i�uaeiou����yY*******************************:**,.;/**-**********";

   var Posic, Carac;
   var TempLog = "";

   for (var i=0; i < campo.value.length; i++) {
	   Carac = campo.value.toUpperCase().charAt (i); // a
	   Posic = Acentos.indexOf (Carac); // 1
	   if (Posic > -1){
	      	TempLog += Traducao.charAt (Posic);
	   } else
	      TempLog += campo.value.toUpperCase().charAt (i);
   }
   campo.value = TempLog.replace( new RegExp(/\*/g), "") ;
}

 //-------------------------------------------------------------------------------//
// Fun��o para retirar caracateres especiais e espacos em branco.
//-------------------------------------------------------------------------------//
function ajustaTextoAcentosCedilha(campo) {
	var Acentos =  "�����������������������������������������_�'@#$!%&*(){}+=`����������|\"\\?:<>,.;/[]-0123456789";  
	var Traducao = "AEIOU���AEIOU�������aeiou��i�uaeiou����yY***************************************************";

   var Posic, Carac;
   var TempLog = "";

   for (var i=0; i < campo.value.length; i++) {
	   Carac = campo.value.toUpperCase().charAt (i); // a
	   Posic = Acentos.indexOf (Carac); // 1
	   if (Posic > -1){
	      	TempLog += Traducao.charAt (Posic);
	   } else
	      TempLog += campo.value.toUpperCase().charAt (i);
   }
   campo.value = TempLog.replace( new RegExp(/\*/g), "") ;
   campo.value = campo.value.trim();
}

function limpaValor(v) {
	var valor_limpo = '';
	var contador;
	for (var i=0; i < v.length; i++) {
		contador = '0123456789'.indexOf(v.substring(i, i+1));
		if (contador >= 0) {
			valor_limpo += contador;
		}
	}
	return valor_limpo;
}

function ajustaTextoCaracteresEspeciaisENumero(campo) {
	var Acentos =  "�����������������������������������������_�'@#$!%&*(){}+=`����������|\"\\?:<>,.;/[]-0123456789";  
	var Traducao = "AEIOU���AEIOU�������aeiou��i�uaeiou����yY********&**********************:**,.;/**-0123456789";

   var Posic, Carac;
   var TempLog = "";

   for (var i=0; i < campo.value.length; i++) {
	   Carac = campo.value.toUpperCase().charAt (i); // a
	   Posic = Acentos.indexOf (Carac); // 1
	   if (Posic > -1){
	      	TempLog += Traducao.charAt (Posic);
	   } else
	      TempLog += campo.value.toUpperCase().charAt (i);
   }
   campo.value = TempLog.replace( new RegExp(/\*/g), "") ;
   campo.value = campo.value.trim();
}

function uppercaseCaracteresEspeciaisENumero(campo) {
	var Acentos =  "�����������������������������������������_�'@#$!%&*(){}+=`����������|\"\\?:<>,.;/[]-0123456789";  
	var Traducao = "AEIOU���AEIOU�������aeiou��i�uaeiou����yY********&**********************:**,.;/**-0123456789";

   var Posic, Carac;
   var TempLog = " ";

   for (var i=0; i < campo.value.length; i++) {
	   Carac = campo.value.toUpperCase().charAt (i); // a
	   Posic = Acentos.indexOf (Carac); // 1
	   if (Posic > -1){
	      TempLog += Traducao.charAt (Posic);
	   } else
	      TempLog += campo.value.toUpperCase().charAt (i);
   }
   campo.value = TempLog.replace( new RegExp(/\*/g), "") ;
   campo.value = campo.value.trim();
}

function limiteTextArea(textarea, limit, infodiv) {
	var text = textarea.value;	
	var textlength = text.length;
	var info = document.getElementById(infodiv);

	if(textlength > limit) {
		info.innerHTML = 'Voc� n�o pode digitar mais de '+limit+' caracteres!';
		textarea.value = text.substr(0,limit);
		return false;
	}
	else {
		info.innerHTML = (limit - textlength) + ' caracteres restantes.';
		return true;
	}
}

function limparTextArea(limit, infodiv) {
	var info = document.getElementById(infodiv);
	info.innerHTML = 'Limite de ' + limit + ' caracteres.';
	return true;
}

// Funcao que inibe e exibe as abas do Wizard.
function loadnext(inibe, exibe) {
 	divInibe = document.getElementById(inibe);
 	divExibe = document.getElementById(exibe);

 	divInibe.style.display = 'none';
 	divExibe.style.display = 'inline';
 }

// Funcao de chamadas das paginas internas do wizard.
function display(objId,value) {
	  var obj = null; 
	  with (document){ 
		  if (getElementById)
			  obj = getElementById(objId); 
	  }
	  if (obj){
		  if (value == 'true'){
			  eval("obj.disabled=true");
		  } else if (value == 'false'){
			  eval("obj.disabled=false");
		  } else {
			  eval("obj.style.display='"+value+"'");
		  }
	  }
	}

//-------------------------------------------------------------------
//Fun��o para carregar o dialog de confirm com layout customizado
//-------------------------------------------------------------------
var lista = new Array();

function confirmaComCallback(mensagem, callback) {
		jConfirm(mensagem, 'Confirma��o', 
			    function(retorno) { 
					if (callback) {
						callback(retorno);
					}
				    return retorno;
			    }
		);
}

function confirma(mensagem, componente, callback, options) {
	var id = jQuery(componente).attr('id');
	var index= jQuery.inArray(id, lista);

	//Nao encontrou o elemento na lista
	if (index == -1) {
		jConfirm(mensagem, 'Confirma&ccedil;&atilde;o', 
			    function(retorno) { 
					if (callback) {
						novoRetorno = callback(retorno);
						if (novoRetorno) {
							retorno = novoRetorno;
						}
					}
					// Adiciona elemento na lista e executa o botao Confirmar
		    		if (retorno) {
		    			//callback();
		    			lista.push(id);
						jQuery(componente).click();
		    		} 
				    return retorno;
			    },
			    options);
		AguardeHide();
		return false;
	} else {
		//Remove o elemento da lista e executa clique do botao
		lista.splice(index,1);
		return true;
	}
	
}

//-------------------------------------------------------------------
//Fun��o para exibir o detalhe da coluna de um registro da tabela. (sub tabela)
//-------------------------------------------------------------------
function exibirDetalhesTabela(linkTituloClass, linkClass){
	jQuery(linkTituloClass).click(function(){
		if ( jQuery(this).hasClass("linkOcultar") ){
			jQuery(this).removeClass("linkOcultar");
			jQuery(linkClass).each( function(){
				alternarExibicao(this, false);
			});				
		} else {
			jQuery(this).addClass("linkOcultar");
			jQuery(linkClass).each( function(){
				alternarExibicao(this, true);
			});
		}
	});

	jQuery(linkClass).click(function(){
		if ( jQuery(this).hasClass("linkOcultar") ){
			alternarExibicao(this, false);
		}else{
			alternarExibicao(this, true);
		}
	});
}
//-------------------------------------------------------------------
//Fun��o para alternar a exibicao do detalhe da coluna de um registro da tabela. (sub tabela)
//-------------------------------------------------------------------
function alternarExibicao(objClass, exibir){
	if ( exibir ){
		jQuery(objClass).text("Ocultar", true)
						.addClass("linkOcultar")
						.parent().parent().parent().next().addClass("TRdetalhe");
						//.parent().parent().parent().next().show();
		//jQuery(objClass).parent().addClass("td3d");
	}else{
		jQuery(objClass).text("Exibir", true)
						.removeClass("linkOcultar")
						//.parent().parent().parent().next().fadeOut("fast");
						.parent().parent().parent().next().removeClass("TRdetalhe");
		//jQuery(objClass).parent().removeClass("td3d");
	}
}

//-------------------------------------------------------------------
//Fun��o para exibir o detalhe da coluna de um registro da tabela. (coluna)
//-------------------------------------------------------------------
function expandirColuna(linkTituloClass, linkClass){
	
	jQuery(linkTituloClass).click(function(){
		
		if ( jQuery(this).hasClass("linkOcultar") ){
			jQuery(this).removeClass("linkOcultar");
			jQuery(linkClass).each( function(){
				alternar(this, false);
			});				
		} else {
			jQuery(this).addClass("linkOcultar");
			jQuery(linkClass).each( function(){
				alternar(this, true);
			});
		}
	});
	
	jQuery(linkClass).bind('click',function() {

			if ( jQuery(this).hasClass("linkOcultar") ){
				alternar(this, false);
			}else{
				alternar(this, true);
			}
		
	});
	
	var tamanhoCabecalho = jQuery(linkTituloClass).parent().width();
	
	//Exibe listas com apenas 1 elemento
	jQuery(linkClass).each(function(){

		//Monta uma div com o mesmo tamanho da coluna do cabe�alho para evitar problema de sobreposi��o de colunas. Mantis: 18768
		jQuery(this).parent().append('<div style="width: '+tamanhoCabecalho+'px; height: 0"></div>');

		if (jQuery(this).next().find('li').length <= '1') {
			jQuery(this).next().find('li').css('list-style-image','none');
			jQuery(this).trigger('click');
		    jQuery(this).remove();
		}
		
		
	});
	
	
}

//-------------------------------------------------------------------
//Fun��o para alternar a exibicao do detalhe da coluna de um registro da tabela. (coluna)
//-------------------------------------------------------------------
function alternar(objClass, exibir){
	
	if ( exibir ){
		jQuery(objClass).text("Ocultar", true)
						.addClass("linkOcultar");
		jQuery(objClass).parent().parent().css('vertical-align','baseline');
		jQuery(objClass).next().show();
		jQuery(objClass).next().css('min-width','125px');

	}else{
		jQuery(objClass).text("Exibir", true)
						.removeClass("linkOcultar");

		jQuery(objClass).next().hide();

	}
}


//-------------------------------------------------------------------
//Fun��o para habilitar e desabilitar componente
//-------------------------------------------------------------------
function desabilitar(name) {

	var componente = jQuery("input[name='"+name+"']");
	
	if (jQuery(componente).attr("disabled"))
		jQuery(componente).attr("disabled",false);
	else
		jQuery(componente).attr("disabled",true);
	
}

//-------------------------------------------------------------------
//Fun��o para habilitar ou desabilitar um componente
//-------------------------------------------------------------------
function desabilitarCondicao(name, condicao) {

	var componente = jQuery("input[name='"+name+"']");
	
	jQuery(componente).attr("disabled",condicao);
	
}

//-------------------------------------------------------------------
//Fun��o para habilitar ou desabilitar um grupo de componentes
//-------------------------------------------------------------------
function desabilitarGrupo(name, condicao) {

	jQuery("div#"+name+" input[type='text'], div#"+name+" select").attr("disabled",condicao);
	
}

//-------------------------------------------------------------------------------//
//Fun��o para visualizar a impress�o de quadros.
//-------------------------------------------------------------------------------//
function popupImpressao(arg0){
	var str = null;
	var lovParam = 'print=true';
	if (arg0.indexOf('?')==-1)
		str = arg0 + '?' + lovParam;
	else
	    str = arg0 + '&' + lovParam;

	var altura = 500;
	var largura = 1000;
var x = parseInt((screen.width-largura)/2);
var y = parseInt((screen.height-altura)/2);

//var win = window.showModalDialog(str, window, "dialogWidth: " + largura + "px; dialogHeight: " + altura + "px; dialogTop: " + x + "; dialogLeft: " + y + "; resizable: 0");

var win = window.open(str, 'lov', 'width='+largura+', height='+altura+', top=' + x + ', left=' + y + ', resizable=yes, toolbar=no, location=no, status=no, menubar=yes, scrollbars=yes, directories=no');
}

//-------------------------------------------------------------------------------//
//Fun��o para posicionar a seta de recolher e expandir menu lateral ao centro.
//-------------------------------------------------------------------------------//
function posicionaSeta(){
	
	altura = jQuery('#menupainel').height();
	alturaMsg = jQuery('#divMensagem').height();

	var meiaAltura = parseFloat(altura)/2;

	var topo = meiaAltura+alturaMsg+84;
	   
   jQuery('#linkSetaOn').animate({top: topo}, 'slow');
   jQuery('#linkSetaOff').css('top',topo);
	
}

function esconderBarra() {

	jQuery('.bgbotao').css('display','none');
	
}

function exibirBarra() {

	//jQuery('.bgbotao').css('display','table-cell');
	jQuery('.bgbotao').show();
	
}

function esconderBarraBotao(condicao) {
	var mostrar = condicao;

	if (mostrar) {
		exibirBarra();
	} else 
		esconderBarra();
}


function expandirLov(componente) {
	
	componente.addClass('lovTextArea');
	
	componente.parent().css('vertical-align','baseline');
	
	componente.mouseover(function(){
		
		var div = jQuery(this);

		var tamanho = jQuery(div).val().length;
		
		if (tamanho > 50) {
			
			var linhas = parseFloat(tamanho) / 45;
			var trunc = Math.ceil(linhas);
			
			jQuery(div).animate({height: "30px"}, function(){	

				jQuery(div).attr('rows', trunc);
				jQuery(div).css('height','auto');
				
			});
			
		}
		
	});

	componente.mouseout(function(){
		
		jQuery(this).animate({height: "13px"}, 200);
		
	});
	
}


function lovChamadaConcluir(arg){
	
	    /*conteudo = jQuery('body');
	    
	    popwidth = conteudo.width;
	    popheight = conteudo.height;*/
		popwidth = screen.width;
		popheight = screen.height;
			
	    popargs = 'width=' + popwidth + ', height=' + popheight+', scrollbars=yes,toolbar=no,location=no,directories=no,status=no, menubar=no,resizable=no';

	    thewindow = window.open(arg, 'Imprimir', popargs);

}

function expandirAutocomplete(componente) {
	
	componente.addClass('ajusteIgnorado');
	componente.addClass('autocomplete');
		
	componente.parent().css('vertical-align','baseline');
	componente.after('<span id="spanExpandir" name="spanExpandir" style="margin-left: '+componente.css('width')+'" >.</span>');
	
	expandirTextArea(componente);
}

function expandirTextArea() {

	var elemento = jQuery('textarea');

	jQuery(elemento).each(function(){

		//Calcula o numero de caracteres que cabem em 1 linha do textarea
		var tamLinha = (jQuery(this).width() * 50) / 309;
		
		var tamanho = jQuery(this).val().length;
		
		if (tamanho > tamLinha) {
			
			var linhas = parseFloat(tamanho) / (tamLinha-5);
			var trunc = Math.ceil(linhas);
				
		} else {
			var trunc = 2;
		}
		
		jQuery(this).attr('rows', trunc);
		jQuery(this).css('height','auto');
	});
	
}


/* --------------------------------
Fun��o para expandir um componente (textArea).
-------------------------------- */
function expandirTextArea(componente) {
	
	var tempo;
	var tempoSaida;
	
	componente.mouseover(function(){
		
		if (typeof(tempo) != 'undefined') {
            clearTimeout(tempo);
        }
		if (typeof(tempoSaida) != 'undefined') {
            clearTimeout(tempoSaida);
        }    
		
		var div = jQuery(this);
        
		tempo = setTimeout(function(){

			var tamanho = jQuery(div).val().length;
			var widthLov = parseFloat(div.css('width'));
			var linhas;
			var trunc;
			
			if ( widthLov <= 309 ){
				linhas = parseFloat(tamanho) / 30;
			} else {
				if ( (widthLov > 309) && (widthLov <= 349)){
					linhas = parseFloat(tamanho) / 50;
				} else {
					if ( (widthLov > 349) && (widthLov <= 409)){
						linhas = parseFloat(tamanho) / 55;
					} else {
						if ( widthLov > 409 ){
							linhas = parseFloat(tamanho) / 60;
						}	
					}
				}	
			}
			trunc = Math.ceil(linhas);
				
			if ( linhas > 1 ){				
				
				jQuery(div).animate({height: "30px"}, function(){	

					jQuery(div).attr('rows', trunc);
					jQuery(div).css('height','auto');
					
				});
				
			}
			}				
			, 1000);
	});

	componente.mouseout(function(){

		if (typeof(tempo) != 'undefined') {
            clearTimeout(tempo);
        }
		if (typeof(tempoSaida) != 'undefined') {
            clearTimeout(tempoSaida);
        }
		
		var div = jQuery(this);
		
		tempoSaida = setTimeout(function(){

			jQuery(div).animate({height: "13px"}, 200);
			
			}				
			, 500);

	});
}

/**
 * 
 * Fixa o cabe�alho de uma tabela
 * 
 * @param height Altura da div
 * @param classContainer class da div na qual a tabela est� contida. 
 * OBS.: Esta class n�o pode repetir para evitar problemas na tela de concluir projeto 
 * @return
 */
function fixedHeader(height, classContainer) {

	//Se n�o tiver listagem
	if (jQuery('div.'+classContainer+' thead').html() == null) {
		return;
	}
	if (height == undefined)
		height = 230;
	
	// Largura da DIV
	var larguraTabela = jQuery('div.'+classContainer+' table').css('width');
	jQuery('div.'+classContainer).css('width',larguraTabela);

	//Copia o cabe�alho original
	var strTableHeader = montarHeader(classContainer, larguraTabela);
	jQuery(strTableHeader).insertBefore('div.'+classContainer);
	
	//Ajusta o estilo das tabelas
	jQuery('div.tableHeader'+classContainer+' table').css('margin' , '0');
	jQuery('div.'+classContainer+' table').css('margin' , '0');
	jQuery('div.'+classContainer).css({'height' : height});
	jQuery('div.'+classContainer).addClass('tableContainer');
	
	var tableHeight = jQuery('.'+classContainer+' table tbody').height() - jQuery('.'+classContainer+' table thead').height();
	if ( tableHeight > height ) {
		//Ajusta o estilo do header caso a tabela tenha scroll
		jQuery('div.tableHeader'+classContainer).addClass('espacamentoHeader');
	} else {
		//Diminui o tamanho da div caso a tabela nao tenha scroll
		jQuery('div.'+classContainer).height('auto');
	}
	
	prepararCabecalho(classContainer);

}
/**
 * Ajusta o tamanho do cabe�alho da tabela (clone) e remove o cabe�alho original
 */
function prepararCabecalho(classContainer) {
	
	var array = new Array();

	var i = 0;
	//Guarda o tamanho das colunas do cabe�alho original
	jQuery('div.'+classContainer+' table thead th').each(function(){

		array[i] = jQuery(this).width();

		i++;
	});
	
	i = 0;
	//Seta o tamanho das colunas para o cabe�alho copiado
	jQuery('div.tableHeader'+classContainer+' table thead th').each(function(){

		jQuery(this).width(array[i]);

		i++;
	});
	
	//Remove o cabe�alho que foi copiado
	jQuery('div.'+classContainer+' thead').remove();
	//jQuery('div.tableContainer thead').hide();

}

function montarHeader(classContainer, larguraTabela) {

	return '<div class="tableHeader'+classContainer+'" style="width:' + larguraTabela + '">'+
				'<table class="listagemHeader" class="rich-table" style="width:100%; border-collapse: collapse; border: 1px solid #EEEEEE">'+
					'<thead class="dr-table-thead">'+
						jQuery('div.'+classContainer+' thead').html()+
					'</thead>'+
				'</table>'+
			'</div>';
	
}

function montarInput(value) {
	
	return '<input type="text" value="'+value+'" disabled=""></input>';
	
}



//-------------------------------------------------------------------
//Fun��o para subir ao TOPO da pagina
//-------------------------------------------------------------------
jQuery(function(){
	jQuery('.ff-control-topo').click(function(){
	 jQuery('html, body').animate({scrollTop: '0px'}, 200);
	return false;
	});
});

//ajustarItemCombo("#{rich:clientId('idParticipante')}");
function ajustarItemCombo(campo){

	if (campo != null){
		var objeto = document.getElementById(campo);
		//jQuery(objeto).addClass(classe);
		var tamanho = jQuery('select[name="'+campo+'"]').css('width');
		var tamanho = tamanho.substring(0,tamanho.length-2);
			
		for (i=0; i<objeto.options.length; i++){
			var tamanhoOptions = Number(tamanho/6.8).toFixed(); 
		
			var item = objeto.options[i];
			item.setAttribute('title',item.text);
			if (item.text.length > tamanhoOptions ){
				item.text = item.text.substring(0,tamanhoOptions) + ' ...';
			}
		}
		var titulo = jQuery('select[name="'+campo+'"] option:selected').attr('title');
		jQuery(objeto).attr('title', titulo);		    	

		jQuery(objeto).change(function() {
			var titulo2 = jQuery('select[name="'+campo+'"] option:selected').attr('title');
			jQuery(objeto).attr('title', titulo2);		    	
		}); 
	 } 	
}


//-------------------------------------------------------------------------------//
//Fun��o para carregar CSS din�micamente.
//-------------------------------------------------------------------------------//
function loadCSS(url) {
var lnk = document.createElement('link');
lnk.setAttribute('type', "text/css" );
lnk.setAttribute('rel', "stylesheet");
lnk.setAttribute('href', url );
document.getElementsByTagName("head").item(0).appendChild(lnk);
}

//-------------------------------------------------------------------------------//
//Fun��o para dimensionar a largura do Scroll Horizontal dos Quadros
//-------------------------------------------------------------------------------//
function carregaScroll(classQuadro){
	
	
	//var janela = jQuery(window).width();
	var janela = jQuery('#main').width();
	//var tamanhoQuadro = jQuery('#conteudo').width();
	var tamanhoQuadro = jQuery('.'+classQuadro).width() + jQuery('#menuesq').width() + 40;
		
    if(tamanhoQuadro > janela)
    { 
    	if (jQuery.browser.msie) { //IE
    		//alert("nome da div: "+classQuadro+" tamanho da Janela: "+tamanhoQuadro+" Main: "+janela);
    			 		tamanho = jQuery('#main').width() - jQuery('#menuesq').width() - jQuery('.fundoMenuLateral').width() - 48;
    	   				jQuery('.scroll').css('width',tamanho+'px');
						jQuery('.scroll').css('overflow-x','scroll');	
		} else { // Firefox
				//alert("nome da div: "+classQuadro+" tamanho da Janela: "+tamanhoQuadro+" Main: "+janela);
	    		    	tamanho = jQuery('#main').width() - jQuery('#menuesq').width() - jQuery('.fundoMenuLateral').width() - 38;
	   					jQuery('.scroll').css('width',tamanho+'px');
						jQuery('.scroll').css('overflow-x','scroll');	
		       }
				     
    	}		 else {
    		 //  alert("nome da div: "+classQuadro+" tamanho da Janela: "+tamanhoQuadro+" Main: "+janela);
        		jQuery('#scroll').css('overflow-x','hidden');	//Nao exibir a barra
		     }	
 }


function removeCss(css) {
	jQuery('link').each(function(){
	   if (jQuery(this).attr('href') == css) {
	        jQuery(this).remove();
	    }
	});
}

/**
 * Fun��o respons�vel por atribuir os estilos �s etapas do wizard
 * 
 * @param indiceEtapa Etapa Selecionada
 * @param ultimaEtapa �ltima etapa v�lida
 * @param desativa Flag para desativar as etapas que n�o s�o acess�veis
 */
function prepararWizard(indiceEtapa, ultimaEtapa, desativa) {
	
	indiceEtapa = indiceEtapa.substring(6,indiceEtapa.length)-1; //Formato: ETAPA_XX
	ultimaEtapa = ultimaEtapa.substring(6,ultimaEtapa.length); //Formato: ETAPA_XX
	var tamanho = jQuery('ul#mainNav li').size()-1;
	
	if (ultimaEtapa == undefined || ultimaEtapa == -1)
		ultimaEtapa = 1;
	
	jQuery('ul#mainNav li').each(function(index){
		var classe = '';

		if (index < (indiceEtapa-1)) {
    		classe = 'done'
		} 
		
		else if (index == (indiceEtapa-1)) {
			classe = 'lastDone';
		}
		
		else if (index == indiceEtapa && index < tamanho) {
			classe = 'current';
		}
		
		else if (index == tamanho && indiceEtapa == tamanho) {
			classe = 'mainNavBg';
		} 
		
		//Seta os estilos at� a ultima etapa v�lida
		if (desativa && index < ultimaEtapa) {
			if (classe == '' && ((index == (ultimaEtapa-2) && tamanho == (ultimaEtapa-1)) ||  (index == (ultimaEtapa-1) && tamanho > (ultimaEtapa-1)) )) 
				classe = 'doneNoBg';
			else if (classe != 'current' && classe != 'lastDone' && !jQuery(this).hasClass('mainNavNoBg') && index < (ultimaEtapa-1))
				classe = 'done';
			else if (classe == 'current' && index < (ultimaEtapa-1) && (index < tamanho-1))  {
				classe = 'currentDone';
			} 
		}
		
		//Seta os estilos para todas as etapas
		if (!desativa) {
			if (classe != 'current' && classe != 'lastDone' && !jQuery(this).hasClass('mainNavNoBg'))
				classe = 'done';
			else if (classe == 'current') 
				classe = 'currentDone';
			else if (jQuery(this).hasClass('mainNavNoBg') && classe != 'mainNavBg')
				classe = 'mainNavBgVerde';
		}
		
		//Remove o click das etapas inativas
		if (desativa) {
			if (classe == '') {
				jQuery(this).children().removeAttr('onclick');
				jQuery(this).children().attr('href','javascript:void(0)');
			}
		}
		
		jQuery(this).addClass(classe);
	    	
	});
	
}

function aplicarMensagemAjuda() {
	jQuery('.linkHelp').each(function() {
		jQuery(this).tipsy({gravity: 'n'});
	});
}

function expandirRecolher(valor) {
		 	
	  var objGroup = jQuery('#menupainel .header');
	 
	  switch(valor){

		case "formulario:expandir":
			objGroup.children("span").addClass("undock");
			objGroup.next().slideDown("slow");
			break;

		case "formulario:recolher":
			objGroup.children("span").removeClass("undock");
			objGroup.next().hide();
			
			break;

		case "formulario:pendentes":
			objGroup.children("span").removeClass("undock");
			objGroup.next().hide();
			
			var objLI = jQuery('#menupainel .icoErro').parent().parent().parent().parent();
			objLI.prev().children("span").addClass("undock");
			objLI.slideDown("slow");
			
			break;	
		}
	  
	   setTimeout("posicionaSeta()", 150);
	   setTimeout("posicionaSeta()", 680);
	 
}

function preencheZeros(param,tamanho)  
{  
   var contador = param.value.length;  
     
   if (param.value.length != tamanho)  
   {  
      do  
      {  
         param.value = "0" + param.value;  
         contador += 1;  
           
      }while (contador <tamanho)  
   }  
}  

function allToUpperCase() {
	var $j = jQuery.noConflict();
	$j(function() {
		j$('input[type=text] , textarea').each(function (index,element){
			element.value = element.value.toUpperCase();
		});
	});
	return true;
}

function selectItem(id,value) {
	var $j = jQuery.noConflict();
	$j(function() {
		if ($j('select[id="formulario:'+id+'"] option:selected').text() == "") {
			$j('select[id="formulario:'+id+'"] option').each(function () {
	            if ($j(this).text() == value) {
	            	$j(this).attr('selected','true');
	            }
	        });
		}
	});
}

function prepararCheckAll(head, body) {
	
	var flag = verificarCheckBox(head,body);

	//Marca o checkbox do head, caso todos estejam marcados
	jQuery(head).attr('checked', flag);
	
	//Prepara o checkbox do head para marcar/desmarcar todos
	jQuery('.checkAllHead').bind('click',function(){
		
		checkAll(head,body);
		
	});
	
	//Prepara os checkbox do body para marcar/desmarcar o checkbox do head
	jQuery('.checkAll').bind('click',function(){
		
		checkHead(jQuery(this),head,body);
		
	});

}

//Fun��o respons�vel por marcar/desmarcar todos os checkBox de uma tabela
function checkAll(head,body) {
	
	var checked = jQuery(head).is(':checked');
	
	jQuery(body).attr('checked', checked);
	
}


//Fun��o respons�vel por marcar/desmarcar o checkbox do head, caso necess�rio 
function checkHead(controle,head,body) {
		
	var checked = jQuery(controle).is(':checked');
	
	if (!checked) {
		jQuery(head).attr('checked', checked);
		return false;
	}
	
	var flag = verificarCheckBox(head,body);
	
	//Marca o checkbox do head, caso todos estejam marcados
	jQuery(head).attr('checked', flag);
	
}

//Verifica se todos os checkbox est�o marcados
function verificarCheckBox(head,body) {
	
	var flag = false;
	
	jQuery(body).each(function(){

		flag = jQuery(this).is(':checked');
		
		if (!flag)
		   return flag;

	});

	return flag;
	
}

// Verifica se pelo menos um checkbox est� marcado.
function verificarPeloMenosUmCheckBox(head,body) {
	
	var flag = false;
	
	jQuery(body).each(function(){

		flag = jQuery(this).is(':checked');
		
		if (flag) {
		   return false;
		}

	});

	return flag;
	
}

function dataMenorQue(base, comparada){
	
	var flag = false;
	var comp = comparada.split("/");    
	var datacomparada = new Date(comp[2], comp[1]-1, comp[0]);
	var bas = base.split("/");    
	var database = new Date(bas[2], bas[1]-1, bas[0]);
	
	if(datacomparada.getTime() < database.getTime()){
		flag = true;
	}
	
	return flag;
}

function somenteNumeros(num) {
    var er = /[^0-9.]/;
    er.lastIndex = 0;
    var campo = num;
    if (er.test(campo.value)) {
      campo.value = "";
    }
}