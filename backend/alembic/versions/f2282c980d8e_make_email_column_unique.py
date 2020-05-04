"""make email column unique

Revision ID: f2282c980d8e
Revises: 0dbfe373e06d
Create Date: 2020-05-04 07:35:21.979866

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "f2282c980d8e"
down_revision = "0dbfe373e06d"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_unique_constraint(None, "users", ["email"])
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, "users", type_="unique")
    # ### end Alembic commands ###