# Registra a tarefa diaria do quantbr para rodar SEM LOGIN.
#
# Usa LogonType S4U ("Service for User"): a tarefa roda com a identidade do usuario
# mesmo sem sessao aberta, e o Windows NAO armazena a senha em lugar nenhum. Precisa de
# elevacao porque conceder S4U mexe no direito "Log on as a batch job" da conta.
#
# Para desfazer:  Unregister-ScheduledTask -TaskName "quantbr-atualizar" -Confirm:$false

$ErrorActionPreference = "Stop"
$usuario = "$env:USERDOMAIN\$env:USERNAME"
$raiz    = "C:\Users\joaoz\quantbr"

$acao = New-ScheduledTaskAction `
    -Execute "$raiz\.venv\Scripts\python.exe" `
    -Argument "atualizar.py" `
    -WorkingDirectory $raiz

# 20:00: o pregao fecha as 18:00 e o arquivo diario da B3 demora a ser publicado.
$gatilho = New-ScheduledTaskTrigger -Daily -At 20:00

$config = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)

$principal = New-ScheduledTaskPrincipal -UserId $usuario -LogonType S4U -RunLevel Limited

Register-ScheduledTask -TaskName "quantbr-atualizar" `
    -Action $acao -Trigger $gatilho -Settings $config -Principal $principal `
    -Description "Atualiza a base de acoes da B3 (quantbr). Roda sem login (S4U), incremental e idempotente." `
    -Force | Out-Null

$t = Get-ScheduledTask -TaskName "quantbr-atualizar"
"OK  usuario=$($t.Principal.UserId)  logon=$($t.Principal.LogonType)  estado=$($t.State)" |
    Out-File "$raiz\_resultado_tarefa.txt" -Encoding utf8
