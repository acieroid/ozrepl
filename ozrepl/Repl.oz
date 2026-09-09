functor
import
   Application
   Browser
   Compiler
   Open
   System
define
   BrowseCounter = {NewCell 0}

   class ClientSocket
      from Open.socket Open.text
   end

   proc {PrintLine Text}
      {System.showInfo Text}
   end

   proc {TerminalBrowse Value}
      Id = @BrowseCounter
   in
      BrowseCounter := Id+1
      %% A Browse entry first shows its current shape. A watcher then waits for
      %% an undetermined top-level value and updates the same entry when it is
      %% bound, preserving Oz's dataflow behaviour.
      {System.showInfo "__OZREPL_BROWSE__"#Id}
      {System.show Value}
      if {IsDet Value} then skip
      else
         thread
            {Wait Value}
            {System.showInfo "__OZREPL_BROWSE_UPDATE__"#Id}
            {System.show Value}
         end
      end
   end

   %% The Python frontend waits for this complete line after every request.
   %% A newline-delimited marker is reliable over a pseudo-terminal, unlike an
   %% inline prompt whose output may remain buffered by Mozart.
   ReadyMarker = "__OZREPL_READY__"

   fun {NewCompiler UseGui}
      Engine = {New Compiler.engine init()}
      %% Keep the stock interface silent. We print its buffered diagnostics
      %% explicitly, so one error cannot make every later query verbose.
      Interface = {New Compiler.interface init(Engine false)}
      BrowseProcedure = if UseGui then Browser.browse else TerminalBrowse end
      Environment = env(
         'Show':System.show
         'Browse':BrowseProcedure
         'Print':System.print
         'System':System
      )
   in
      %% Queries submitted to one engine are processed sequentially. Installing
      %% this small convenience environment before user input therefore makes
      %% Show, Print, and System available in every later fragment.
      {Engine enqueue(mergeEnv(Environment))}
      {Interface sync()}
      compiler(engine:Engine interface:Interface)
   end

   fun {ReportErrors Interface}
      HasErrors = {Interface hasErrors($)}
   in
      if HasErrors then
         {System.printInfo {Interface getVS($)}}
      end
      {Interface reset()}
      HasErrors
   end

   proc {Evaluate CompilerState Source}
      try
         {CompilerState.engine enqueue(feedVirtualString(Source))}
         {CompilerState.interface sync()}
         _ = {ReportErrors CompilerState.interface}
      catch Error then
         {System.showError Error}
      end
   end


   proc {EvaluateExpression CompilerState Source}
      ResultRecord = return(result:_)
   in
      try
         {CompilerState.engine enqueue([
            setSwitch(expression true)
            feedVirtualString(Source ResultRecord)
            setSwitch(expression false)
         ])}
         {CompilerState.interface sync()}
         if {ReportErrors CompilerState.interface} then skip
         else {System.show ResultRecord.result}
         end
      catch Error then
         {System.showError Error}
      end
   end

   proc {LoadFile CompilerState FileName}
      try
         {CompilerState.engine enqueue(feedFile(FileName))}
         {CompilerState.interface sync()}
         _ = {ReportErrors CompilerState.interface}
      catch Error then
         {System.showError Error}
      end
   end

   fun {LoadArgument Line}
      case {String.tokens Line & }
      of [":load" FileName] then some(FileName)
      else none
      end
   end

   fun {HexDigit C}
      if C >= &0 andthen C =< &9 then C-&0
      elseif C >= &a andthen C =< &f then C-&a+10
      elseif C >= &A andthen C =< &F then C-&A+10
      else raise invalidHexDigit(C) end
      end
   end

   fun {DecodeHex Text}
      case Text
      of nil then nil
      [] High|Low|Rest then
         (16*{HexDigit High}+{HexDigit Low})|{DecodeHex Rest}
      else
         raise invalidHexMessage(Text) end
      end
   end

   proc {Loop Client CompilerState UseGui}
      {PrintLine ReadyMarker}
      Encoded
      Message
      Tag
      Source
   in
      %% Python owns terminal input and sends each complete fragment as one
      %% newline-delimited hexadecimal line over a persistent local socket.
      Encoded = {Client getS($)}
      Message = if Encoded == false then false else {DecodeHex Encoded} end
      if Message == false then
         Tag = &S
         Source = false
      else
         Tag|Source = Message
      end
      if Source == false orelse Source == ":quit" then
         {PrintLine "bye"}
         {Client close}
         {Application.exit 0}
      elseif Source == nil then
         {Loop Client CompilerState UseGui}
      elseif Source == ":no-gui" then
         {Loop Client {NewCompiler false} false}
      elseif Source == ":reset" then
         if UseGui then {Browser.close} else skip end
         {PrintLine "compiler environment reset"}
         {Loop Client {NewCompiler UseGui} UseGui}
      else
         if Tag == &F then
            if UseGui then {Browser.close} else skip end
            {LoadFile CompilerState Source}
            {Loop Client CompilerState UseGui}
         else case {LoadArgument Source}
         of some(FileName) then
            {LoadFile CompilerState FileName}
            {Loop Client CompilerState UseGui}
         [] none then
            if Tag == &E then {EvaluateExpression CompilerState Source}
            else {Evaluate CompilerState Source}
            end
            {Loop Client CompilerState UseGui}
         end
         end
      end
   end
   Server Client Port
in
   Server = {New Open.socket init}
   Port = {Server bind(port:$)}
   {Server listen}
   {PrintLine "__OZREPL_PORT__"#Port}
   {Server accept(acceptClass:ClientSocket accepted:Client)}
   {Server close}
   {Loop Client {NewCompiler true} true}
end
