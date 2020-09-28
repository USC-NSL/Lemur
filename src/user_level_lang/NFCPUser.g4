/*
 * NFCPUser.g4
 *
 * This is the ANTLR grammar file for the NFCP user-level configuration language.
 * We aim to provide the following syntax.
 * - define NF instances
 * - define flow spec
 * - associate several flow spec(s) with a NF instance
 * - define arguments
 *
 */

grammar NFCPUser ;


/*
 * Parser Rules
 */

total : ( line+ ) EOF ;

line : ( define_int | define_float | define_string | define_bool
	| define_nfinstance | define_nlist | define_ntuple | define_nlinkedlist
	| define_flowspec | define_nfchain | config_nfchain )? NEWLINE ;

define_int : VARIABLENAME '=' INT ;

define_float : VARIABLENAME '=' FLOAT ;

define_string : VARIABLENAME '=' STRING ;

define_bool : VARIABLENAME '=' BOOL ;

define_nfinstance : 'func' VARIABLENAME '=' netfunction ;

define_nlist : VARIABLENAME '=' nlist ;

define_ntuple : VARIABLENAME '=' ntuple ;

define_nlinkedlist: VARIABLENAME '=' nlinkedlist ;

/*
 * Define Flowspec and NF Chain. Configure NF Chain
 * Note: 
 * - type(flowspec) must be nlist whose elements must be tuple
 * - type(netfunction_chain) must be nlinkedlist whose elements must be netfunction
 */

define_flowspec : 'flow' VARIABLENAME '=' flowspec ;

define_nfchain : 'chain' VARIABLENAME '=' netfunction_chain ;

config_nfchain : VARIABLENAME ':' VARIABLENAME ;


/*
 * Network Functions
 * - type(flowspec) = nList
 * - type(netfunction_chain) = nlinkedlist
 * - type(netfunction) = function with brackets
 */

flowspec : nlist ;

netfunction_chain : nlinkedlist ;

netfunction : ( VARIABLENAME '(' ')' 
	| VARIABLENAME '(' VARIABLENAME ')'
	| VARIABLENAME '(' nlist ')' | VARIABLENAME '(' ntuple ')' ) ;

/*
 * Structured Data Types
 */

nlist : '[' ( nlist_elem (',' nlist_elem)* ) ']' ;

nlist_elem : ( ntuple | INT | FLOAT | STRING | VARIABLENAME ) ;

ntuple : '{' ( ntuple_elem (',' ntuple_elem)* ) '}' ;

ntuple_elem : (STRING) ':' ( STRING | INT | FLOAT | VARIABLENAME | nlist | nlinkedlist ) ;

nlinkedlist : ( nlinkedlist_elem ( '->' nlinkedlist_elem )* ) ;

nlinkedlist_elem : ( netfunction | VARIABLENAME | nlist ) ;


/*
 * Lexer Rules
 */

MULTILINECOMMENT : '/*' .*? '*/' -> skip ;
SINGLELINECOMMENT : '//' ~[\r\n]* -> skip ;
WHITESPACE : ( ' ' | '\t' )+ -> skip ; 
NEWLINE : ('\r'? '\n' | '\r')+ ;

fragment LOWERCASE : [a-z];
fragment UPPERCASE : [A-Z];
fragment DIGIT : [0-9];


/*
 * Numbers
 */
INT : (DIGIT)+ ;
FLOAT : (DIGIT)+ '.' (DIGIT)*
	| '.' (DIGIT)+ ;


/*
 * String
 */
STRING : ( '\'' WILDCARD '\'' | '"' .*? '"' ) ;
fragment WILDCARD : .*? ;

/*
 * Bool
 */
BOOL : ( 'False' | 'True' ) ;


/* Variable Name */
VARIABLENAME : (LOWERCASE | UPPERCASE | DIGIT | '_' )+ ;

