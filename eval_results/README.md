# 评测结果挂载目录

生产 Compose 将本目录只读挂载到容器的 `/app/eval_results`。

仓库只保留经过确认、可公开的结构化人工评分 `_human_review.json`。原始 `report_case*_off/guarded.json`、平台响应、内部地址、Payload、接入信息和其他正式结果包文件不得提交到公开仓库。

正式服务器上的完整结果包由受控目录维护；CD 只同步脱敏人工评分文件，不删除或覆盖其他结果文件。
