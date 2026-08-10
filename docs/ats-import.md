# ATS 导入边界

AIHR 现在提供 `aihr.data_sources.ats.import_ats_csv`，用于企业授权后的
ATS 导出导入。ATS（候选人跟踪系统）中的投递、联系、面试、Offer 和入职
流程会进入推荐事实与漏斗事件表。

导入必须同时满足：

- `AIHR_ATS_IMPORT_AUTHORIZATION` 中保存授权票据的 SHA-256 值；
- `AIHR_ATS_HASH_SALT` 已配置；
- CSV 字段和阶段值通过校验；
- 事件引用已导入的推荐记录。

外部候选人、职位、招聘人员和模型标识在写库前会加盐哈希，原始标识不会
进入 AIHR 数据库。当前适配器只支持经过脱敏的 CSV 导出，尚未声称已经连接
任何具体 ATS 厂商 API；生产接入前还需要完成厂商授权、字段映射和回放测试。
