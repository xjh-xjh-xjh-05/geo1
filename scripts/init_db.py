"""
初始化默认管理员账号
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.core.database import SessionLocal, engine, Base
from api.core.security import get_password_hash
from api.models.db_models import User, Tenant

def init_db():
    """初始化数据库并创建默认管理员"""
    
    # 创建表
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    
    try:
        # 创建默认租户
        tenant = db.query(Tenant).filter(Tenant.code == "default").first()
        if not tenant:
            tenant = Tenant(
                name="默认租户",
                code="default",
                status="active",
                contact_email="admin@geo-detection.local"
            )
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
            print(f"✅ 创建默认租户：{tenant.name} (ID={tenant.id})")
        
        # 创建默认管理员账号
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            admin = User(
                username="admin",
                email="admin@geo-detection.local",
                password_hash=get_password_hash("admin123"),
                tenant_id=tenant.id,
                role="admin",
                status="active",
                permissions=["*"]
            )
            db.add(admin)
            db.commit()
            print("✅ 创建默认管理员账号:")
            print("   用户名：admin")
            print("   密码：admin123")
        else:
            print("ℹ️  管理员账号已存在")
        
        # 创建测试用户
        test_user = db.query(User).filter(User.username == "test").first()
        if not test_user:
            test_user = User(
                username="test",
                email="test@geo-detection.local",
                password_hash=get_password_hash("test123"),
                tenant_id=tenant.id,
                role="user",
                status="active"
            )
            db.add(test_user)
            db.commit()
            print("✅ 创建测试用户账号:")
            print("   用户名：test")
            print("   密码：test123")
        else:
            print("ℹ️  测试用户账号已存在")
        
        print("\n✅ 数据库初始化完成!")
        
    except Exception as e:
        db.rollback()
        print(f"❌ 初始化失败：{str(e)}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    init_db()
