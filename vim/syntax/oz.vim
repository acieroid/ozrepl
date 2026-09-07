" Oz syntax highlighting for ozrepl, based on Mozart's oz.el categories.
if exists("b:current_syntax")
  finish
endif

syn case match
syn keyword ozKeyword declare local in end proc fun functor require prepare
syn keyword ozKeyword import export define at case then else of elseof elsecase
syn keyword ozKeyword if elseif class from prop attr feat meth self div mod
syn keyword ozKeyword andthen orelse cond or dis choice not thread try catch
syn keyword ozKeyword finally raise lock skip fail for do suchthat
syn keyword ozConstant true false unit

syn match ozVariable "\<[A-Z_][[:alnum:]_]*\>"
syn match ozNumber "\<\d\+\%([.]\d\+\)\?\>"
syn match ozNumber "\<0[xX][0-9A-Fa-f]\+\>"
syn match ozOperator "\[\]\|:::\?\|:=\|==\|\\=\|=<\|>=\|[!#|.@,~*/+<>=-]"
syn match ozDirective "\\[A-Za-z][^[:space:]]*"
syn match ozCharacter "&\%(\\\%([0-7]\{3}\|x[0-9A-Fa-f]\{2}\|[abfnrtv'\"`]\)\|.\)"
syn region ozString start=+"+ skip=+\\.+ end=+"+
syn region ozAtom start=+'+ skip=+\\.+ end=+'+
syn region ozQuotedVariable start=+`+ skip=+\\.+ end=+`+
syn match ozComment "%.*$"

hi def link ozKeyword Keyword
hi def link ozConstant Constant
hi def link ozVariable Identifier
hi def link ozNumber Number
hi def link ozOperator Operator
hi def link ozDirective PreProc
hi def link ozCharacter Character
hi def link ozString String
hi def link ozAtom String
hi def link ozQuotedVariable Identifier
hi def link ozComment Comment

let b:current_syntax = "oz"
